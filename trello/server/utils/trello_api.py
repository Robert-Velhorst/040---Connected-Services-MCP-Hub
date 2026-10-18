# trello_api.py
import asyncio
import logging
import random
import re
import time
from typing import Optional

import httpx

from server.exceptions import (
    BadRequestError,
    ForbiddenError,
    RateLimitError,
    ResourceNotFoundError,
    TransientBlockError,
    TrelloMCPError,
    UnauthorizedError,
)

# Configure logging
logger = logging.getLogger(__name__)

TRELLO_API_BASE = "https://api.trello.com/1"
_SECRET_QUERY_VALUE = re.compile(r"(?i)(key|token)=([^&\s]+)")

# Trello's edge answers with an HTML bot-check page instead of JSON. Never send
# a browser-like User-Agent: a "Mozilla/5.0" UA is rejected outright with 405,
# while httpx's own default UA is accepted. Leave the UA alone.
_BOT_CHECK_STATUSES = {405, 407, 503}


def _redact_secrets(value: str) -> str:
    return _SECRET_QUERY_VALUE.sub(r"\1=[REDACTED]", value)


def _looks_like_bot_check(response: httpx.Response) -> bool:
    """True when Trello returned an interstitial HTML page rather than JSON."""
    if response.status_code not in _BOT_CHECK_STATUSES:
        return False
    content_type = response.headers.get("content-type", "")
    return "html" in content_type.lower()


class _RateLimiter:
    """Adaptive token bucket shared by every request from one client.

    Measured ceilings: 100 req/10s per token, 300/10s per key, 375/10s per
    member. The per-token budget binds first, so the default of 5 req/s sits at
    half the allowance and leaves burst headroom in the bucket.

    Staying under the documented limits is necessary but not sufficient: the
    edge also applies a reputation penalty to *sustained* heavy use. A first
    full crawl ran clean at 5 req/s while an immediate second crawl saw three
    boards blocked out. So the bucket self-throttles -- each block divides the
    effective rate, each success decays the penalty back toward normal.
    """

    MAX_PENALTY = 16.0

    def __init__(self, rate_per_second: float, burst: int | None = None):
        self.rate = max(0.2, rate_per_second)
        self.capacity = burst if burst is not None else max(1, int(self.rate * 2))
        self._tokens = float(self.capacity)
        self._updated = time.monotonic()
        self._penalty = 1.0
        self._lock = asyncio.Lock()

    @property
    def effective_rate(self) -> float:
        return max(0.1, self.rate / self._penalty)

    def penalize(self) -> None:
        self._penalty = min(self.MAX_PENALTY, self._penalty * 2.0)
        logger.info(
            "Throttling down to %.2f req/s after an edge block", self.effective_rate
        )

    def recover(self) -> None:
        if self._penalty > 1.0:
            # Decay gently: recovering as fast as we backed off just re-trips
            # the same reputation penalty.
            self._penalty = max(1.0, self._penalty * 0.97)

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                rate = self.effective_rate
                now = time.monotonic()
                self._tokens = min(
                    self.capacity, self._tokens + (now - self._updated) * rate
                )
                self._updated = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                await asyncio.sleep((1.0 - self._tokens) / rate)


class TrelloClient:
    """
    Client class for interacting with the Trello API over REST.
    Includes enhanced error handling, retry logic, and rate limit management.
    """

    def __init__(
        self,
        api_key: str,
        token: str,
        max_retries: int = 5,
        requests_per_second: float | None = None,
    ):
        self.api_key = api_key
        self.token = token
        self.base_url = TRELLO_API_BASE
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=60.0)
        self._limiter = (
            _RateLimiter(requests_per_second) if requests_per_second else None
        )

    async def close(self):
        await self.client.aclose()

    def _handle_http_error(
        self, error: httpx.HTTPStatusError, endpoint: str, method: str
    ):
        """
        Handle HTTP errors with specific exception types based on status code.

        Args:
            error: The HTTP status error
            endpoint: The API endpoint that was called
            method: The HTTP method used

        Raises:
            Specific TrelloMCPError subclass based on status code
        """
        status_code = error.response.status_code

        # Bot-check interstitials carry a full HTML page; logging it verbatim
        # buries the real signal, and it must be retried rather than raised.
        if _looks_like_bot_check(error.response):
            logger.warning(
                "Trello edge returned an HTML bot-check for %s %s (HTTP %s)",
                method,
                endpoint,
                status_code,
            )
            raise TransientBlockError(endpoint, status_code)

        response_text = _redact_secrets(error.response.text)

        logger.error(
            f"HTTP {status_code} error for {method} {endpoint}: {response_text}"
        )

        if status_code == 400:
            raise BadRequestError(
                f"Invalid request to {endpoint}. {response_text or 'Please check your parameters.'}"
            )
        elif status_code == 401:
            raise UnauthorizedError()
        elif status_code == 403:
            raise ForbiddenError("Resource", endpoint, "access")
        elif status_code == 404:
            # Extract resource type from endpoint
            resource_type = endpoint.split("/")[1].rstrip("s").capitalize()
            resource_id = endpoint.split("/")[2] if len(endpoint.split("/")) > 2 else "unknown"
            raise ResourceNotFoundError(resource_type, resource_id)
        elif status_code == 429:
            retry_after = error.response.headers.get("Retry-After")
            raise RateLimitError(
                retry_after=int(retry_after) if retry_after else None
            )
        else:
            raise TrelloMCPError(
                f"HTTP {status_code} error for {method} {endpoint}: {response_text}",
                status_code=status_code,
            )

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
    ):
        """
        Execute a request with exponential backoff retry for rate limits.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint
            params: Query parameters
            data: Request body data

        Returns:
            Response JSON

        Raises:
            TrelloMCPError or subclass on failure
        """
        base_delay = 1

        for attempt in range(self.max_retries):
            try:
                if self._limiter is not None:
                    await self._limiter.acquire()
                if method == "GET":
                    result = await self._get(endpoint, params)
                elif method == "POST":
                    result = await self._post(endpoint, params, data)
                elif method == "PUT":
                    result = await self._put(endpoint, params, data)
                elif method == "DELETE":
                    result = await self._delete(endpoint, params)
                else:
                    raise TrelloMCPError(f"Unsupported HTTP method {method}")
                if self._limiter is not None:
                    self._limiter.recover()
                return result
            except TransientBlockError:
                if self._limiter is not None:
                    self._limiter.penalize()
                if attempt == self.max_retries - 1:
                    logger.error(
                        f"Trello kept blocking {method} {endpoint} after "
                        f"{self.max_retries} attempts"
                    )
                    raise

                # Jitter matters: several boards retrying in lockstep would
                # re-collide. Capped so a long backoff cannot stall the crawl.
                delay = min(30.0, base_delay * (2**attempt)) + random.uniform(0, 2.0)
                logger.warning(
                    f"Bot-check block on attempt {attempt + 1}/{self.max_retries}. "
                    f"Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
            except RateLimitError as e:
                if attempt == self.max_retries - 1:
                    logger.error(f"Max retries exceeded for {method} {endpoint}")
                    raise

                delay = e.retry_after or (base_delay * (2**attempt))
                logger.warning(
                    f"Rate limit hit on attempt {attempt + 1}/{self.max_retries}. "
                    f"Retrying in {delay} seconds..."
                )
                await asyncio.sleep(delay)
            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt == self.max_retries - 1:
                    logger.error(f"Max retries exceeded for {method} {endpoint}")
                    raise TrelloMCPError(
                        f"Network error after {self.max_retries} attempts: "
                        f"{_redact_secrets(str(e))}"
                    )

                delay = base_delay * (2**attempt)
                logger.warning(
                    f"Network error on attempt {attempt + 1}/{self.max_retries}. "
                    f"Retrying in {delay} seconds... Error: {_redact_secrets(str(e))}"
                )
                await asyncio.sleep(delay)

        raise TrelloMCPError(f"Max retries exceeded for {method} {endpoint}")

    async def _get(self, endpoint: str, params: Optional[dict] = None):
        """Internal GET method without retry logic."""
        all_params = {"key": self.api_key, "token": self.token}
        if params:
            all_params.update(params)

        try:
            response = await self.client.get(endpoint, params=all_params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e, endpoint, "GET")
        except httpx.RequestError as e:
            logger.error("Request error: %s", _redact_secrets(str(e)))
            raise

    async def _post(
        self, endpoint: str, params: Optional[dict] = None, data: Optional[dict] = None
    ):
        """Internal POST method without retry logic."""
        all_params = {"key": self.api_key, "token": self.token}
        if params:
            all_params.update(params)

        try:
            response = await self.client.post(endpoint, params=all_params, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e, endpoint, "POST")
        except httpx.RequestError as e:
            logger.error("Request error: %s", _redact_secrets(str(e)))
            raise

    async def _put(
        self, endpoint: str, params: Optional[dict] = None, data: Optional[dict] = None
    ):
        """Internal PUT method without retry logic."""
        all_params = {"key": self.api_key, "token": self.token}
        if params:
            all_params.update(params)

        try:
            response = await self.client.put(endpoint, params=all_params, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e, endpoint, "PUT")
        except httpx.RequestError as e:
            logger.error("Request error: %s", _redact_secrets(str(e)))
            raise

    async def _delete(self, endpoint: str, params: Optional[dict] = None):
        """Internal DELETE method without retry logic."""
        all_params = {"key": self.api_key, "token": self.token}
        if params:
            all_params.update(params)

        try:
            response = await self.client.delete(endpoint, params=all_params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e, endpoint, "DELETE")
        except httpx.RequestError as e:
            logger.error("Request error: %s", _redact_secrets(str(e)))
            raise

    # Public methods with retry logic
    async def GET(self, endpoint: str, params: Optional[dict] = None):
        """
        Execute a GET request with retry logic.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            Response JSON
        """
        return await self._request_with_retry("GET", endpoint, params=params)

    async def POST(
        self, endpoint: str, data: Optional[dict] = None, params: Optional[dict] = None
    ):
        """
        Execute a POST request with retry logic.

        Args:
            endpoint: API endpoint
            data: Request body data
            params: Query parameters

        Returns:
            Response JSON
        """
        return await self._request_with_retry("POST", endpoint, params=params, data=data)

    async def PUT(
        self, endpoint: str, data: Optional[dict] = None, params: Optional[dict] = None
    ):
        """
        Execute a PUT request with retry logic.

        Args:
            endpoint: API endpoint
            data: Request body data
            params: Query parameters

        Returns:
            Response JSON
        """
        return await self._request_with_retry("PUT", endpoint, params=params, data=data)

    async def DELETE(self, endpoint: str, params: Optional[dict] = None):
        """
        Execute a DELETE request with retry logic.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            Response JSON
        """
        return await self._request_with_retry("DELETE", endpoint, params=params)
