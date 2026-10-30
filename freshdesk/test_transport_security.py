"""Additional outbound authority cases; no provider requests or account credentials."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ["FRESHDESK_DOMAIN"] = "example.freshdesk.com"
os.environ["FRESHDESK_API_KEY"] = "test_key"
sys.path.insert(0, str(Path(__file__).parent))

import main as freshdesk


@pytest.mark.parametrize("value", [
    "localhost", "127.0.0.1", "169.254.169.254", "[::1]", "evil.example",
    "freshdesk.com", "example.freshdesk.com.evil.example",
    "evil.example.freshdesk.com", "example-freshdesk.com",
    "https://user@example.freshdesk.com", "https://@example.freshdesk.com",
    "https://example.freshdesk.com:443", "https://example.freshdesk.com:",
    "http://example.freshdesk.com", "https://example.freshdesk.com/api/v2",
    "https://example.freshdesk.com?token=test", "https://example.freshdesk.com#fragment",
    "https://exa\nmple.freshdesk.com", "https://exa\rmple.freshdesk.com",
    "https://exa\tmple.freshdesk.com", "examp\u217ce.freshdesk.com",
    "-example.freshdesk.com", "example-.freshdesk.com",
    "a" * 64 + ".freshdesk.com",
])
def test_non_tenant_authorities_are_rejected(value):
    with pytest.raises(ValueError):
        freshdesk.normalize_domain(value)


@pytest.mark.parametrize("value, expected", [
    ("a.freshdesk.com", "a.freshdesk.com"),
    ("https://Example-Team.Freshdesk.com/", "example-team.freshdesk.com"),
    ("example.freshdesk.com.", "example.freshdesk.com"),
])
def test_tenant_authorities_are_canonical(value, expected):
    assert freshdesk.normalize_domain(value) == expected


@pytest.mark.parametrize("endpoint", [
    "", "/tickets", "//evil.example/tickets", "https://evil.example/tickets",
    "../tickets", "tickets/../agents", "tickets/%2e%2e/agents",
    "tickets?host=evil.example", "tickets#fragment", "tickets\\agents",
    "tickets\n", "tickets//7",
])
def test_ambiguous_resource_paths_do_not_reach_transport(monkeypatch, endpoint):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid endpoint reached transport")

    monkeypatch.setattr(freshdesk.requests, "request", forbidden)
    assert "relative API resource path" in freshdesk.safe_request("GET", endpoint)["error"]


@pytest.mark.parametrize("status", [300, 301, 302, 303, 307, 308, 399])
def test_redirects_fail_without_followup_or_retry(monkeypatch, status):
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return SimpleNamespace(status_code=status)

    def forbidden_sleep(*args):
        raise AssertionError("redirect must not be retried")

    monkeypatch.setattr(freshdesk.requests, "request", request)
    monkeypatch.setattr(freshdesk.time, "sleep", forbidden_sleep)
    result = freshdesk.safe_request("GET", "tickets/7", allow_redirects=True)
    assert result == {"error": "Freshdesk redirects are not permitted", "status_code": status}
    assert len(calls) == 1
    assert calls[0][1] == "https://example.freshdesk.com/api/v2/tickets/7"
    assert calls[0][2]["allow_redirects"] is False


def test_query_values_remain_parameters_on_fixed_provider_authority(monkeypatch):
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None,
                               json=lambda: {"results": []})

    monkeypatch.setattr(freshdesk.requests, "request", request)
    params = {"query": "https://evil.example/metadata"}
    assert freshdesk.safe_request("GET", "search/tickets", params=params) == {"results": []}
    assert calls[0][1] == "https://example.freshdesk.com/api/v2/search/tickets"
    assert calls[0][2]["params"] == params
    assert calls[0][2]["allow_redirects"] is False
