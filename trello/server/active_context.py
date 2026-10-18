"""Session-scoped Trello board and workspace selection for MCP tools."""

from dataclasses import dataclass

from mcp.server.mcpserver import Context


@dataclass
class TrelloContextSelection:
    board_id: str | None = None
    workspace_id: str | None = None


class ActiveContextStore:
    def __init__(self) -> None:
        self._selections: dict[str, TrelloContextSelection] = {}

    @staticmethod
    def _session_key(ctx: Context) -> str:
        if ctx.client_id:
            return f"client:{ctx.client_id}"
        return f"session:{id(ctx.session)}"

    def get(self, ctx: Context) -> TrelloContextSelection:
        return self._selections.setdefault(self._session_key(ctx), TrelloContextSelection())

    def set_board(self, ctx: Context, board_id: str) -> TrelloContextSelection:
        selection = self.get(ctx)
        selection.board_id = board_id
        return selection

    def set_workspace(self, ctx: Context, workspace_id: str) -> TrelloContextSelection:
        selection = self.get(ctx)
        selection.workspace_id = workspace_id
        return selection

    def clear(self, ctx: Context) -> None:
        self._selections.pop(self._session_key(ctx), None)

    def resolve_board(self, ctx: Context, board_id: str | None) -> str:
        if board_id:
            return board_id
        active_board = self.get(ctx).board_id
        if not active_board:
            raise ValueError("board_id is required until set_active_board has been called for this session")
        return active_board

    def resolve_workspace(self, ctx: Context, workspace_id: str | None) -> str:
        if workspace_id:
            return workspace_id
        active_workspace = self.get(ctx).workspace_id
        if not active_workspace:
            raise ValueError("workspace_id is required until set_active_workspace has been called for this session")
        return active_workspace


active_context = ActiveContextStore()
