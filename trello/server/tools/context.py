"""MCP tools for selecting a default Trello board and workspace per session."""

from mcp.server.mcpserver import Context

from server.active_context import active_context


async def set_active_board(ctx: Context, board_id: str) -> dict[str, str]:
    """Set the default board for this MCP session."""
    active_context.set_board(ctx, board_id)
    return {"active_board_id": board_id}


async def set_active_workspace(ctx: Context, workspace_id: str) -> dict[str, str]:
    """Set the default workspace for this MCP session."""
    active_context.set_workspace(ctx, workspace_id)
    return {"active_workspace_id": workspace_id}


async def get_active_context(ctx: Context) -> dict[str, str | None]:
    """Return the current session's default board and workspace."""
    selection = active_context.get(ctx)
    return {"active_board_id": selection.board_id, "active_workspace_id": selection.workspace_id}


async def clear_active_context(ctx: Context) -> dict[str, bool]:
    """Clear this MCP session's default board and workspace."""
    active_context.clear(ctx)
    return {"cleared": True}
