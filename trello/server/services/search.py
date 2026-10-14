"""
Service for Trello search operations.
"""

from typing import List, Optional, Dict, Any
from server.utils.trello_api import TrelloClient


class SearchService:
    """Service for search and filtering operations."""

    def __init__(self, client: TrelloClient):
        """
        Initialize the search service.

        Args:
            client: Trello API client instance
        """
        self.client = client

    async def search(
        self,
        query: str,
        id_boards: Optional[str] = None,
        id_organizations: Optional[str] = None,
        model_types: Optional[str] = None,
        partial: bool = False
    ) -> Dict[str, Any]:
        """
        Search across Trello resources.

        Args:
            query: Search query string
            id_boards: Comma-separated list of board IDs to search
            id_organizations: Comma-separated list of organization IDs to search
            model_types: Comma-separated list of model types (cards, boards, members, organizations)
            partial: Enable partial matching

        Returns:
            Dictionary containing search results by type
        """
        params: Dict[str, Any] = {
            "query": query,
            # Trello caps results at 10 per model type unless asked otherwise.
            # 1000 is the documented ceiling; 2000 returns HTTP 400.
            "cards_limit": 1000,
            "boards_limit": 1000,
            "organizations_limit": 1000,
            "card_fields": "all",
            "card_board": "true",
            "card_list": "true",
            # Prefix matching is off by default, so "invoic" would miss
            # "invoices". Callers can still disable it explicitly.
            "partial": "true" if partial else "false",
        }

        # Without idBoards the search silently narrows; "mine" spans every
        # board the token can reach.
        params["idBoards"] = id_boards or "mine"
        if id_organizations:
            params["idOrganizations"] = id_organizations
        if model_types:
            params["modelTypes"] = model_types

        return await self.client.GET("/search", params=params)

    async def search_members(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        """
        Search for members.

        Args:
            query: Search query string
            limit: Maximum number of results (default 8, max 20)

        Returns:
            List of member objects
        """
        params = {
            "query": query,
            "limit": min(limit, 20)
        }

        return await self.client.GET("/search/members", params=params)
