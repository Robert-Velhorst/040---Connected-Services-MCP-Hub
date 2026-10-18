"""Register the complete Trello MCP tool surface with safety annotations."""

import os

from mcp.types import ToolAnnotations

from server import settings
from server.tools import (
    advanced_card,
    analytics,
    attachment,
    batch,
    board,
    card,
    checklist,
    comment,
    complete,
    context,
    custom_field,
    export,
    label,
    list,
    member,
    search,
    webhook,
    workspace,
    compat,
)


def _title(tool) -> str:
    return tool.__name__.replace("_", " ").title()


def _register(mcp, tools, *, read_only: bool) -> None:
    for tool in tools:
        annotations = ToolAnnotations(
            title=_title(tool),
            readOnlyHint=read_only,
            destructiveHint=not read_only,
        )
        try:
            mcp.add_tool(tool, annotations=annotations)
        except TypeError as error:
            if "annotations" not in str(error):
                raise
            # Keep registration testable with minimal mock MCP implementations.
            mcp.add_tool(tool)


def _read_only_from_environment() -> bool:
    # Delegated to settings so the flag resolves identically whether the value
    # comes from the MCP client's env block or the package-anchored .env.
    return settings.read_only()


def register_tools(mcp, *, read_only: bool | None = None):
    """Register tools, optionally omitting all mutation-capable operations.

    ``TRELLO_READ_ONLY=true`` creates a server-side boundary: write tools are
    not registered or advertised, rather than merely being labelled risky.
    """
    if read_only is None:
        read_only = _read_only_from_environment()

    # Cache-backed tools first: they are the ones that can answer questions
    # spanning all 85 boards inside Codex's 60s tool timeout, so they should be
    # the most prominent in tool discovery. All of them are strictly read-only
    # (trello_refresh only *reads* from Trello into the local mirror).
    if settings.cache_enabled():
        _register(
            mcp,
            (
                complete.trello_search_cards,
                complete.trello_get_card,
                complete.trello_list_boards,
                complete.trello_list_workspaces,
                complete.trello_board_cards,
                complete.trello_account_overview,
                complete.trello_sync_status,
                complete.trello_refresh,
                complete.trello_set_archived_visibility,
                complete.trello_get_settings,
            ),
            read_only=True,
        )

    _register(
        mcp,
        (
            board.get_board,
            board.get_boards,
            board.get_open_board_count,
            board.get_board_labels,
            list.get_list,
            list.get_lists,
            card.get_card,
            card.get_cards,
            card.get_board_cards,
            card.search_cards,
            checklist.get_checklist,
            checklist.get_card_checklists,
            label.get_card_labels,
            comment.get_card_comments,
            comment.get_card_actions,
            comment.get_board_actions,
            attachment.get_card_attachments,
            member.get_board_members,
            member.get_workspace_members,
            member.get_member,
            member.get_card_members,
            webhook.get_webhook,
            webhook.list_webhooks,
            workspace.get_workspaces,
            workspace.get_workspace,
            workspace.get_workspace_boards,
            custom_field.get_board_custom_fields,
            custom_field.get_card_custom_field_values,
            search.search_trello,
            search.search_members,
            batch.batch_get_resources,
            export.export_board,
            export.list_organization_exports,
            analytics.get_board_statistics,
            analytics.get_card_cycle_time,
            context.get_active_context,
            compat.overview,
            compat.search,
            compat.fetch,
        ),
        read_only=True,
    )
    if read_only:
        return

    _register(
        mcp,
        (
            board.create_board_label,
            board.create_board,
            board.update_board,
            board.delete_board,
            list.create_list,
            list.update_list,
            list.delete_list,
            card.create_card,
            card.update_card,
            card.delete_card,
            card.archive_card,
            card.add_comment_to_card,
            card.add_member_to_card,
            card.remove_member_from_card,
            checklist.create_checklist,
            checklist.update_checklist,
            checklist.delete_checklist,
            checklist.add_checkitem,
            checklist.update_checkitem,
            checklist.delete_checkitem,
            label.update_label,
            label.delete_label,
            label.add_label_to_card,
            label.remove_label_from_card,
            comment.add_comment,
            comment.update_comment,
            comment.delete_comment,
            attachment.attach_url,
            attachment.delete_attachment,
            attachment.set_attachment_as_cover,
            member.add_board_member,
            member.update_board_member,
            member.remove_board_member,
            member.add_card_member,
            member.remove_card_member,
            webhook.create_webhook,
            webhook.update_webhook,
            webhook.delete_webhook,
            workspace.create_workspace,
            workspace.update_workspace,
            workspace.delete_workspace,
            custom_field.create_custom_field,
            custom_field.update_custom_field,
            custom_field.delete_custom_field,
            custom_field.set_custom_field_value_checkbox,
            custom_field.set_custom_field_value_text,
            custom_field.set_custom_field_value_number,
            custom_field.set_custom_field_value_date,
            custom_field.set_custom_field_value_list,
            custom_field.add_custom_field_option,
            custom_field.update_custom_field_option,
            custom_field.delete_custom_field_option,
            export.create_organization_export,
            export.create_board_from_template,
            advanced_card.set_card_due_date,
            advanced_card.set_card_due_complete,
            advanced_card.subscribe_to_card,
            advanced_card.unsubscribe_from_card,
            advanced_card.vote_on_card,
            advanced_card.remove_vote_from_card,
            advanced_card.set_card_start_date,
            context.set_active_board,
            context.set_active_workspace,
            context.clear_active_context,
            compat.move_card,
        ),
        read_only=False,
    )
