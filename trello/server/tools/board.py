"""
This module contains tools for managing Trello boards.
"""

import logging
from typing import List

from mcp.server.mcpserver import Context

from server.models import TrelloBoard, TrelloLabel, TrelloMember
from server.dtos.create_label import CreateLabelPayload
from server.dtos.create_board import CreateBoardPayload
from server.dtos.update_board import UpdateBoardPayload
from server.services.board import BoardService
from server.validators import ValidationService
from server.trello import client
from server.exceptions import TrelloMCPError
from server.active_context import active_context

logger = logging.getLogger(__name__)

service = BoardService(client)
validator = ValidationService(client)


async def get_board(ctx: Context, board_id: str | None = None) -> TrelloBoard:
    """Retrieves a specific board by its ID.

    Args:
        board_id (str): The ID of the board to retrieve.

    Returns:
        TrelloBoard: The board object containing board details.
    """
    try:
        board_id = active_context.resolve_board(ctx, board_id)
        logger.info(f"Getting board with ID: {board_id}")
        result = await service.get_board(board_id)
        logger.info(f"Successfully retrieved board: {board_id}")
        return result
    except Exception as e:
        error_msg = f"Failed to get board: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        raise


async def get_boards(
    ctx: Context, limit: int = 10, offset: int = 0
) -> List[TrelloBoard]:
    """Returns a compact, paginated list of open boards.

    The former implementation returned every field of every board in one
    response. That is a poor fit for connector clients, which can reject an
    otherwise successful response when it is too large. This compact
    discovery response keeps the initial request usable and includes enough
    information to select a board for the detail tools. It deliberately keeps
    the original list-shaped result, so existing ChatGPT connector
    registrations continue to understand the response.

    Args:
        limit: Maximum number of boards to return (1-25).
        offset: Zero-based position in the ordered set of open boards.

    Returns:
        A compact page of open boards.
    """
    try:
        safe_limit = min(max(limit, 1), 25)
        safe_offset = max(offset, 0)
        logger.info("Getting a compact page of open boards")
        boards = await service.get_boards()
        open_boards = [board for board in boards if not board.closed]
        page = open_boards[safe_offset : safe_offset + safe_limit]
        result = [
            TrelloBoard(
                id=board.id,
                name=board.name,
                url=board.url,
            )
            for board in page
        ]
        logger.info(
            "Successfully retrieved %s of %s open boards",
            len(page),
            len(open_boards),
        )
        return result
    except Exception as e:
        error_msg = f"Failed to get boards: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        raise


async def get_open_board_count(ctx: Context) -> dict[str, int]:
    """Returns a compact count of the authenticated user's open Trello boards.

    This read-only overview avoids transferring board names and other board
    details when a client only needs to confirm that Trello data is available.

    Returns:
        A dictionary containing the number of open boards.
    """
    try:
        logger.info("Counting open boards")
        boards = await service.get_boards()
        open_board_count = sum(not board.closed for board in boards)
        logger.info("Successfully counted open boards")
        return {"open_board_count": open_board_count}
    except Exception as e:
        error_msg = f"Failed to count open boards: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        raise


async def get_board_labels(ctx: Context, board_id: str | None = None) -> List[TrelloLabel]:
    """Retrieves all labels for a specific board.

    Args:
        board_id (str): The ID of the board whose labels to retrieve.

    Returns:
        List[TrelloLabel]: A list of label objects for the board.
    """
    try:
        board_id = active_context.resolve_board(ctx, board_id)
        logger.info(f"Getting labels for board: {board_id}")
        result = await service.get_board_labels(board_id)
        logger.info(f"Successfully retrieved {len(result)} labels for board: {board_id}")
        return result
    except Exception as e:
        error_msg = f"Failed to get board labels: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        raise


async def get_board_members(ctx: Context, board_id: str | None = None) -> List[TrelloMember]:
    """Retrieves all members of a specific board.

    Args:
        board_id (str): The ID of the board whose members to retrieve.

    Returns:
        List[TrelloMember]: A list of member objects with id, fullName, and username.
    """
    try:
        board_id = active_context.resolve_board(ctx, board_id)
        logger.info(f"Getting members for board: {board_id}")
        result = await service.get_board_members(board_id)
        logger.info(f"Successfully retrieved {len(result)} members for board: {board_id}")
        return result
    except Exception as e:
        error_msg = f"Failed to get board members: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        raise


async def create_board_label(ctx: Context, payload: CreateLabelPayload, board_id: str | None = None) -> TrelloLabel:
    """Create label for a specific board.

    Args:
        board_id (str): The ID of the board whose to add label to.
        payload (CreateLabelPayload): The label creation payload.

    Returns:
        TrelloLabel: A label object for the board.
    """
    try:
        board_id = active_context.resolve_board(ctx, board_id)
        logger.info(f"Creating label {payload.name} label for board: {board_id}")
        # Validate board exists
        await validator.validate_board_exists(board_id)
        result = await service.create_board_label(board_id, **payload.model_dump(exclude_unset=True))
        logger.info(f"Successfully created label {payload.name} for board: {board_id}")
        return result
    except TrelloMCPError as e:
        error_msg = f"Failed to create board label: {e.message}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        raise
    except Exception as e:
        error_msg = f"Failed to create board label: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        raise


async def create_board(ctx: Context, payload: CreateBoardPayload) -> TrelloBoard:
    """Create a new Trello board.

    Args:
        payload (CreateBoardPayload): The board creation payload containing name, description,
                                     organization, and preferences.

    Returns:
        TrelloBoard: The newly created board object.
    """
    try:
        logger.info(f"Creating board: {payload.name}")

        # Validate organization exists if specified
        if payload.id_organization:
            await validator.validate_organization_exists(payload.id_organization)
            await validator.validate_organization_membership(payload.id_organization)

        result = await service.create_board(**payload.model_dump(exclude_unset=True))
        logger.info(f"Successfully created board: {result.id} - {result.name}")
        return result
    except TrelloMCPError as e:
        error_msg = f"Failed to create board: {e.message}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        raise
    except Exception as e:
        error_msg = f"Failed to create board: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        raise


async def update_board(ctx: Context, payload: UpdateBoardPayload, board_id: str | None = None) -> TrelloBoard:
    """Update an existing Trello board.

    Args:
        board_id (str): The ID of the board to update.
        payload (UpdateBoardPayload): The board update payload containing fields to update.

    Returns:
        TrelloBoard: The updated board object.
    """
    try:
        board_id = active_context.resolve_board(ctx, board_id)
        logger.info(f"Updating board: {board_id}")

        # Validate board exists
        await validator.validate_board_exists(board_id)

        # Validate organization exists if moving board
        if payload.id_organization:
            await validator.validate_organization_exists(payload.id_organization)
            await validator.validate_organization_membership(payload.id_organization)

        # Convert payload to API parameters
        params = payload.to_api_params()

        result = await service.update_board(board_id, **params)
        logger.info(f"Successfully updated board: {board_id}")
        return result
    except TrelloMCPError as e:
        error_msg = f"Failed to update board: {e.message}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        raise
    except Exception as e:
        error_msg = f"Failed to update board: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        raise


async def delete_board(ctx: Context, board_id: str | None = None) -> dict:
    """Delete a Trello board permanently.

    Args:
        board_id (str): The ID of the board to delete.

    Returns:
        dict: Confirmation of deletion.
    """
    try:
        board_id = active_context.resolve_board(ctx, board_id)
        logger.info(f"Deleting board: {board_id}")

        # Validate board exists and user has admin permission
        await validator.validate_board_exists(board_id)
        await validator.validate_board_admin_permission(board_id)

        await service.delete_board(board_id)
        logger.info(f"Successfully deleted board: {board_id}")
        return {"success": True, "message": f"Board {board_id} has been permanently deleted"}
    except TrelloMCPError as e:
        error_msg = f"Failed to delete board: {e.message}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        raise
    except Exception as e:
        error_msg = f"Failed to delete board: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        raise
