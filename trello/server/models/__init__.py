"""Public Trello data models used by tools and services.

Every model here inherits ``extra="allow"``. That is load-bearing, not
cosmetic: pydantic's default is to *silently discard* undeclared fields, and
Trello returns 67 top-level keys on a card while this module only ever named
16. Measured against a real card, ``TrelloCard(**response)`` threw away 75% of
the payload -- including ``checklists`` (the actual work items), ``badges``,
``customFieldItems``, ``dateLastActivity``, ``members``, ``idLabels``,
``shortUrl`` and ``actions``. Losing those is exactly the "cannot extract all
information present in cards" symptom.

Optional-with-default is likewise deliberate. Trello omits fields whenever a
caller narrows ``fields=``, and a required field would turn a partial response
into a hard ValidationError mid-crawl.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict

from .action import TrelloAction
from .attachment import TrelloAttachment
from .custom_field import (
    TrelloCustomField,
    TrelloCustomFieldItem,
    TrelloCustomFieldOption,
)
from .member import TrelloMember
from .webhook import TrelloWebhook


class _TrelloModel(BaseModel):
    """Base that preserves every field Trello sends."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class TrelloBoard(_TrelloModel):
    id: str
    name: str | None = None
    desc: str | None = None
    closed: bool = False
    idOrganization: str | None = None
    url: str | None = None
    shortUrl: str | None = None
    shortLink: str | None = None
    dateLastActivity: str | None = None


class TrelloList(_TrelloModel):
    id: str
    name: str | None = None
    closed: bool = False
    idBoard: str | None = None
    pos: float | None = None


class TrelloLabel(_TrelloModel):
    id: str
    name: str | None = None
    color: str | None = None


class TrelloComment(_TrelloModel):
    id: str
    author_id: str | None = None
    author_name: str | None = None
    date: str | None = None
    text: str = ""


class TrelloCard(_TrelloModel):
    id: str
    name: str | None = None
    desc: str | None = None
    closed: bool = False
    idList: str | None = None
    idBoard: str | None = None
    url: str | None = None
    shortUrl: str | None = None
    shortLink: str | None = None
    idShort: int | None = None
    pos: float | None = None
    labels: list[TrelloLabel] = []
    idLabels: list[str] = []
    due: str | None = None
    start: str | None = None
    dueComplete: bool = False
    dateLastActivity: str | None = None
    idMembers: list[str] = []
    idMemberCreator: str | None = None
    cover: Dict[str, Any] | None = None
    badges: Dict[str, Any] | None = None
    subscribed: bool = False
    isTemplate: bool = False
    attachments: list[Dict[str, Any]] = []
    checklists: list[Dict[str, Any]] = []
    customFieldItems: list[Dict[str, Any]] = []
    members: list[Dict[str, Any]] = []
    comments: list[TrelloComment] = []


class TrelloOrganization(_TrelloModel):
    id: str
    name: str | None = None
    displayName: str | None = None
    desc: Optional[str] = None
    url: str | None = None
    idEnterprise: Optional[str] = None
    prefs: Optional[dict] = None
    memberships: Optional[list] = None


__all__ = [
    "TrelloAction",
    "TrelloAttachment",
    "TrelloBoard",
    "TrelloCard",
    "TrelloComment",
    "TrelloCustomField",
    "TrelloCustomFieldItem",
    "TrelloCustomFieldOption",
    "TrelloLabel",
    "TrelloList",
    "TrelloMember",
    "TrelloOrganization",
]
