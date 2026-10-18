"""
MCP tools for advanced card features.
"""

from mcp.server.mcpserver import Context
from server.trello import client
from server.validators.validation_service import ValidationService

validator = ValidationService(client)


async def set_card_due_date(
    card_id: str,
    due_date: str,
    ctx: Context
) -> str:
    """
    Set a due date on a card.

    Args:
        card_id: The ID of the card
        due_date: Due date in ISO format (e.g., 2024-12-31T23:59:59.000Z) or null to remove

    Returns:
        Confirmation message
    """
    # Using global validator

    # Validate card exists
    await validator.validate_card_exists(card_id)

    # Set due date
    params = {"due": due_date if due_date != "null" else None}
    await client.PUT(f"/cards/{card_id}", data=params)

    return f"Set due date for card {card_id} to {due_date}"



async def set_card_due_complete(
    card_id: str,
    complete: bool,
    ctx: Context
) -> str:
    """
    Mark a card's due date as complete or incomplete.

    Args:
        card_id: The ID of the card
        complete: True to mark complete, False to mark incomplete

    Returns:
        Confirmation message
    """
    # Using global validator

    # Validate card exists
    await validator.validate_card_exists(card_id)

    # Set due complete
    params = {"dueComplete": complete}
    await client.PUT(f"/cards/{card_id}", data=params)

    status = "complete" if complete else "incomplete"
    return f"Marked card {card_id} due date as {status}"



async def subscribe_to_card(ctx: Context, card_id: str) -> str:
    """
    Subscribe to a card to receive notifications about updates.

    Args:
        card_id: The ID of the card

    Returns:
        Confirmation message
    """
    # Using global validator

    # Validate card exists
    await validator.validate_card_exists(card_id)

    # Subscribe
    params = {"subscribed": "true"}
    await client.PUT(f"/cards/{card_id}", data=params)

    return f"Subscribed to card {card_id}"



async def unsubscribe_from_card(ctx: Context, card_id: str) -> str:
    """
    Unsubscribe from a card to stop receiving notifications.

    Args:
        card_id: The ID of the card

    Returns:
        Confirmation message
    """
    # Using global validator

    # Validate card exists
    await validator.validate_card_exists(card_id)

    # Unsubscribe
    params = {"subscribed": "false"}
    await client.PUT(f"/cards/{card_id}", data=params)

    return f"Unsubscribed from card {card_id}"



async def vote_on_card(
    card_id: str,
    member_id: str,
    ctx: Context
) -> str:
    """
    Add a vote to a card (requires voting to be enabled on the board).

    Args:
        card_id: The ID of the card
        member_id: The ID of the member voting

    Returns:
        Confirmation message
    """
    # Using global validator

    # Validate card exists
    await validator.validate_card_exists(card_id)

    # Add vote
    params = {"value": member_id}
    await client.POST(f"/cards/{card_id}/idMembersVoted", data=params)

    return f"Added vote from member {member_id} to card {card_id}"



async def remove_vote_from_card(
    card_id: str,
    member_id: str,
    ctx: Context
) -> str:
    """
    Remove a vote from a card.

    Args:
        card_id: The ID of the card
        member_id: The ID of the member whose vote to remove

    Returns:
        Confirmation message
    """
    # Using global validator

    # Validate card exists
    await validator.validate_card_exists(card_id)

    # Remove vote
    await client.DELETE(f"/cards/{card_id}/idMembersVoted/{member_id}")

    return f"Removed vote from member {member_id} on card {card_id}"



async def set_card_start_date(
    card_id: str,
    start_date: str,
    ctx: Context
) -> str:
    """
    Set a start date on a card.

    Args:
        card_id: The ID of the card
        start_date: Start date in ISO format (e.g., 2024-01-01T00:00:00.000Z) or null to remove

    Returns:
        Confirmation message
    """
    # Using global validator

    # Validate card exists
    await validator.validate_card_exists(card_id)

    # Set start date
    params = {"start": start_date if start_date != "null" else None}
    await client.PUT(f"/cards/{card_id}", data=params)

    return f"Set start date for card {card_id} to {start_date}"
