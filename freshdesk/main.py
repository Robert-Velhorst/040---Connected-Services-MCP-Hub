#!/usr/bin/env python3
"""Freshdesk MCP connector with resilient, non-blocking HTTP helpers."""

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv
from fastmcp import FastMCP

# Stderr is captured by the operator's process manager; file logging is explicit.
_handlers = [logging.StreamHandler()]
if _log_file := os.getenv("FRESHDESK_LOG_FILE"):
    _handlers.append(logging.FileHandler(_log_file, encoding="utf-8"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=_handlers)
logger = logging.getLogger("FreshdeskMCP")


def normalize_domain(value: str) -> str:
    """Accept only an HTTPS Freshdesk tenant authority, never an arbitrary host."""
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("FRESHDESK_DOMAIN must not contain control characters")
    raw = value.strip()
    if not raw:
        return ""

    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.netloc.lower() != parsed.hostname
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("FRESHDESK_DOMAIN must contain only a hostname")
    hostname = parsed.hostname.removesuffix(".").lower()
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.freshdesk\.com", hostname):
        raise ValueError("FRESHDESK_DOMAIN must be a tenant.freshdesk.com hostname")
    return hostname


def _positive_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return max(1, int(value))
    except ValueError:
        logger.warning("Ignoring invalid %s value", name)
        return default


load_dotenv(Path(__file__).with_name(".env"), override=False)
FRESHDESK_DOMAIN = normalize_domain(os.getenv("FRESHDESK_DOMAIN", ""))
FRESHDESK_API_KEY = os.getenv("FRESHDESK_API_KEY")
FRESHDESK_SEARCH_MAX_PAGES = _positive_int_env("FRESHDESK_SEARCH_MAX_PAGES", 10)
FRESHDESK_TICKETS_PER_PAGE = 100

if not FRESHDESK_DOMAIN or not FRESHDESK_API_KEY:
    raise ValueError("Missing FRESHDESK_DOMAIN or FRESHDESK_API_KEY in environment variables")

FRESHDESK_TENANT = FRESHDESK_DOMAIN.removesuffix(".freshdesk.com")
BASE_URL = f"https://{FRESHDESK_TENANT}.freshdesk.com/api/v2"


def _error_response(message: str, status_code: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"error": message}
    if status_code is not None:
        result["status_code"] = status_code
    return result


def _retry_after_seconds(response: requests.Response) -> int:
    try:
        return max(1, min(int(response.headers.get("Retry-After", "2")), 60))
    except ValueError:
        return 2


def safe_request(method: str, endpoint: str, **kwargs) -> Any:
    """Perform one Freshdesk request with bounded retry for rate limits and I/O."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", endpoint):
        return _error_response("Freshdesk endpoint must be a relative API resource path")
    # Callers cannot re-enable redirects or send the account credential elsewhere.
    kwargs["allow_redirects"] = False
    retries = 3
    for attempt in range(retries):
        try:
            response = requests.request(
                method,
                f"{BASE_URL}/{endpoint}",
                auth=(FRESHDESK_API_KEY, "X"),
                timeout=20,
                **kwargs,
            )
            if 300 <= response.status_code < 400:
                return _error_response("Freshdesk redirects are not permitted", response.status_code)
            if response.status_code == 429 and attempt < retries - 1:
                time.sleep(_retry_after_seconds(response))
                continue
            response.raise_for_status()
            if response.status_code == 204:
                return {}
            try:
                return response.json()
            except ValueError:
                return {}
        except requests.exceptions.HTTPError as error:
            status_code = error.response.status_code if error.response is not None else None
            logger.warning("Freshdesk request failed with HTTP %s", status_code)
            return _error_response("Freshdesk request failed", status_code)
        except requests.exceptions.RequestException as error:
            logger.warning("Attempt %s/%s failed (%s)", attempt + 1, retries, type(error).__name__)
            if attempt < retries - 1:
                time.sleep(2)
    return _error_response(f"Max retries reached for {endpoint}")


async def fd_get(endpoint: str, params: dict[str, Any] | None = None) -> Any:
    """Run a blocking Freshdesk GET without blocking the MCP event loop."""
    return await asyncio.to_thread(safe_request, "GET", endpoint, params=params)


async def fd_post(endpoint: str, data: dict[str, Any]) -> Any:
    """Run a blocking Freshdesk POST without blocking the MCP event loop."""
    return await asyncio.to_thread(safe_request, "POST", endpoint, json=data)


async def fd_put(endpoint: str, data: dict[str, Any]) -> Any:
    """Run a blocking Freshdesk PUT without blocking the MCP event loop."""
    return await asyncio.to_thread(safe_request, "PUT", endpoint, json=data)


async def list_tickets_for_search() -> list[dict[str, Any]] | dict[str, Any]:
    """Page through tickets when the Freshdesk search API is unavailable."""
    tickets: list[dict[str, Any]] = []
    for page in range(1, FRESHDESK_SEARCH_MAX_PAGES + 1):
        batch = await fd_get("tickets", params={"page": page, "per_page": FRESHDESK_TICKETS_PER_PAGE})
        if isinstance(batch, dict) and "error" in batch:
            return batch
        if not isinstance(batch, list):
            return _error_response("Freshdesk returned an unexpected ticket list response")
        tickets.extend(batch)
        if len(batch) < FRESHDESK_TICKETS_PER_PAGE:
            break
    return tickets


server = FastMCP(
    name="Freshdesk MCP Connector",
    instructions="Access, search, and manage Freshdesk tickets via MCP tools.",
)


@server.tool(description="Get account overview including agents and groups")
async def overview() -> dict[str, Any]:
    """Get basic Freshdesk account info."""
    agents, groups = await asyncio.gather(fd_get("agents"), fd_get("groups"))
    return {"company": {"domain": FRESHDESK_DOMAIN}, "agents": agents, "groups": groups}


@server.tool(description="Search tickets by keyword (works in all plans)")
async def search(query: str) -> dict[str, Any]:
    """Search ticket subjects and descriptions, with a paginated free-plan fallback."""
    query = query.strip()
    if not query:
        return {"results": []}

    data = await fd_get("search/tickets", params={"query": f'"{query}"'})
    if isinstance(data, dict) and data.get("status_code") in {403, 404}:
        logger.warning("Search endpoint unavailable, falling back to paginated tickets")
        tickets = await list_tickets_for_search()
    elif isinstance(data, dict) and "error" in data:
        return data
    else:
        tickets = data.get("results", data) if isinstance(data, dict) else data

    if isinstance(tickets, dict) and "error" in tickets:
        return tickets
    if not isinstance(tickets, list):
        return _error_response("Freshdesk returned an unexpected search response")

    results = []
    lowered_query = query.lower()
    for ticket in tickets:
        if not isinstance(ticket, dict):
            continue
        subject = (ticket.get("subject") or "").lower()
        description = (ticket.get("description_text") or ticket.get("description") or "").lower()
        if lowered_query in subject or lowered_query in description:
            results.append(
                {
                    "id": ticket.get("id"),
                    "subject": ticket.get("subject", "No Subject"),
                    "status": ticket.get("status"),
                    "priority": ticket.get("priority"),
                    "url": f"https://{FRESHDESK_DOMAIN}/a/tickets/{ticket.get('id')}",
                }
            )
    return {"results": results}


@server.tool(description="Fetch detailed info about a specific ticket")
async def fetch(ticket_id: int) -> dict[str, Any]:
    """Fetch a ticket and its conversations."""
    ticket = await fd_get(f"tickets/{ticket_id}")
    if not isinstance(ticket, dict):
        return _error_response("Freshdesk returned an unexpected ticket response")
    if "error" in ticket:
        return ticket

    conversations = await fd_get(f"tickets/{ticket_id}/conversations")
    if not isinstance(conversations, list):
        conversations = []
    return {
        "id": ticket.get("id"),
        "subject": ticket.get("subject"),
        "description": ticket.get("description_text"),
        "status": ticket.get("status"),
        "priority": ticket.get("priority"),
        "type": ticket.get("type"),
        "created_at": ticket.get("created_at"),
        "updated_at": ticket.get("updated_at"),
        "conversations": conversations,
        "url": f"https://{FRESHDESK_DOMAIN}/a/tickets/{ticket_id}",
    }


@server.tool(description="Create a new Freshdesk ticket")
async def create_ticket(email: str, subject: str, description: str, priority: int = 1, status: int = 2) -> Any:
    return await fd_post(
        "tickets",
        {"email": email, "subject": subject, "description": description, "priority": priority, "status": status},
    )


@server.tool(description="Update ticket status, priority, or description")
async def update_ticket(
    ticket_id: int,
    status: int | None = None,
    priority: int | None = None,
    description: str | None = None,
) -> Any:
    data: dict[str, Any] = {}
    if status is not None:
        data["status"] = status
    if priority is not None:
        data["priority"] = priority
    if description is not None:
        data["description"] = description
    if not data:
        return _error_response("Provide at least one ticket field to update")
    return await fd_put(f"tickets/{ticket_id}", data)


@server.tool(description="Reply or add a private note to a ticket")
async def reply(ticket_id: int, body: str, private: bool = False) -> Any:
    return await fd_post(f"tickets/{ticket_id}/reply", {"body": body, "private": private})


@server.tool(description="Close a ticket (set status = 5)")
async def close_ticket(ticket_id: int) -> Any:
    return await fd_put(f"tickets/{ticket_id}", {"status": 5})


@server.tool(description="Ping the connector to verify it's running")
async def ping() -> dict[str, str]:
    return {"status": "ok", "domain": FRESHDESK_DOMAIN}


if __name__ == "__main__":
    host = os.getenv("FRESHDESK_MCP_HOST", "127.0.0.1")
    log_host = host.replace("\r", "").replace("\n", "")
    logger.info("Starting Freshdesk MCP connector on %s:8001", log_host)
    server.run(transport="sse", host=host, port=8001)
