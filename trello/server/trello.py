import logging

from server import settings
from server.utils.trello_api import TrelloClient

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Credentials come from server.settings, which anchors .env to the package
# directory. A bare load_dotenv() resolves relative to the working directory,
# and the ChatGPT/Codex app spawns this server with an arbitrary CWD -- so the
# old behaviour meant the server died at import with "must be set in
# environment variables" despite a correctly filled .env sitting right there.
api_key = settings.api_key()
token = settings.api_token()

if not api_key or not token:
    raise ValueError(
        "TRELLO_API_KEY and TRELLO_TOKEN must be set. Checked the process "
        f"environment and {settings.PACKAGE_ROOT / '.env'}. When launching from "
        "the ChatGPT app or Codex, either fill that .env or set them in the "
        "[mcp_servers.trello] env block of ~/.codex/config.toml."
    )

client = TrelloClient(
    api_key=api_key,
    token=token,
    max_retries=settings.max_retries(),
    requests_per_second=settings.requests_per_second(),
)
logger.info("Trello client and service initialized successfully")


# Add a prompt for common Trello operations
def trello_help() -> str:
    """Provides help information about available Trello operations."""
    return """
    Available Trello Operations:
    1. Complete extraction (local mirror, spans every board and workspace):
       - trello_search_cards: full-text search over names, descriptions,
         checklist items and comments across the whole account
       - trello_get_card: one card with every field, checklists included
       - trello_board_cards: page all cards on a board, archived included
       - trello_account_overview / trello_list_boards / trello_list_workspaces
       - trello_sync_status / trello_refresh
    2. Board Operations:
       - Get a specific board
       - List all boards
       - Get board labels
       - Add label to a board
    3. List Operations:
       - Get a specific list
       - List all lists in a board
       - Create a new list
       - Update a list's name
       - Archive a list
    4. Card Operations:
       - Get a specific card
       - List all cards in a list
       - Get every card on a board (get_board_cards)
       - Create a new card
       - Update a card's attributes
       - Delete a card
    5. Checklist Operations:
       - Get a specific checklist
       - List all checklists in a card
       - Create a new checklist
       - Update a checklist
       - Delete a checklist
       - Add checkitem to checklist
       - Update checkitem
       - Delete checkitem
    """
