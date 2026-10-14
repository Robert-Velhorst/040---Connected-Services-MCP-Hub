"""Compatibility tools retained from the former lightweight Trello server."""

from mcp.server.mcpserver import Context

from server.dtos.update_card import UpdateCardPayload
from server.tools import board, card, workspace


async def overview(ctx: Context) -> dict:
    """Return the authenticated user's workspaces and boards.

    This read-only alias preserves the former lightweight ``overview`` entry
    point. Use ``get_workspaces`` and ``get_boards`` for the typed APIs.
    """
    return {
        "workspaces": await workspace.get_workspaces(ctx),
        "boards": await board.get_boards(ctx),
    }


async def search(ctx: Context, query: str) -> dict:
    """Search cards using the former lightweight-server tool name.

    For additional Trello search filters, use ``search_trello``.
    """
    return {"results": await card.search_cards(ctx, query)}


async def fetch(ctx: Context, card_id: str) -> dict:
    """Fetch a card and its comments using the former lightweight name."""
    return {
        "card": await card.get_card(ctx, card_id),
        "comments": await card.get_card_comments(ctx, card_id),
    }


async def move_card(ctx: Context, card_id: str, list_id: str):
    """Move a card to a list; retained for lightweight-server clients."""
    return await card.update_card(ctx, card_id, UpdateCardPayload(idList=list_id))
