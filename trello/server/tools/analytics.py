"""
from server.validators import ValidationService
MCP tools for analytics and reporting.
"""

import json
from mcp.server.mcpserver import Context
from server.trello import client
from server.services.analytics import AnalyticsService
from server.validators.validation_service import ValidationService
from server.active_context import active_context

service = AnalyticsService(client)
validator = ValidationService(client)


async def get_board_statistics(ctx: Context, board_id: str | None = None) -> str:
    """
    Get comprehensive statistics and metrics for a board.

    Provides insights including:
    - Total counts (lists, cards, members, labels)
    - Card status breakdown (open, closed, overdue, completed)
    - Cards per list distribution
    - Label usage statistics
    - Member activity metrics

    Args:
        board_id: The ID of the board

    Returns:
        JSON string containing comprehensive board statistics
    """
    # Using global validator
    # Using global service

    board_id = active_context.resolve_board(ctx, board_id)
    # Validate board exists
    await validator.validate_board_exists(board_id)

    # Get statistics
    stats = await service.get_board_statistics(board_id)

    return f"Board Statistics for '{stats['board_name']}':\n" \
           f"- {stats['total_lists']} lists, {stats['total_cards']} total cards\n" \
           f"- {stats['open_cards']} open, {stats['closed_cards']} closed\n" \
           f"- {stats['overdue_cards']} overdue, {stats['completed_cards']} completed\n" \
           f"- {stats['total_members']} members, {stats['total_labels']} labels\n\n" \
           f"Full statistics: {json.dumps(stats, indent=2)}"



async def get_card_cycle_time(ctx: Context, board_id: str | None = None) -> str:
    """
    Calculate average time cards spend in each list (cycle time analysis).

    This helps identify bottlenecks in your workflow by showing how long
    cards typically stay in each list before moving to the next stage.

    Args:
        board_id: The ID of the board

    Returns:
        JSON string containing cycle time statistics per list
    """
    # Using global validator
    # Using global service

    board_id = active_context.resolve_board(ctx, board_id)
    # Validate board exists
    await validator.validate_board_exists(board_id)

    # Get cycle time
    cycle_data = await service.get_card_cycle_time(board_id)

    return f"Card Cycle Time Analysis:\n{json.dumps(cycle_data, indent=2)}"
