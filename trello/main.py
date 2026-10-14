import logging
import os
import sys

from mcp.server.fastmcp import FastMCP
from starlette.routing import Route

from server import settings
from server.tools.tools import register_tools

# Windows consoles default to cp1252, which cannot encode characters that
# appear in real Trello data -- this account has a checklist named with a
# zero-width space (U+200B). Logging such a name to a cp1252 stream raises
# UnicodeEncodeError and kills the server. Force UTF-8 before any handler is
# attached.
for _stream in (sys.stderr, sys.stdout):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - detached stream
            pass

# Configure logging.
#
# In stdio mode the MCP protocol owns stdout: anything printed there corrupts
# the JSON-RPC stream and the client drops the connection. Logs therefore go to
# stderr explicitly rather than relying on basicConfig's default.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
# Trello credentials are carried in query parameters. Keep HTTP client request
# logs below INFO so those URLs cannot leak into normal server logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Environment is loaded by server.settings, anchored to this file's directory
# rather than the current working directory.


# Initialize MCP server
# ChatGPT can make independent Streamable HTTP requests instead of preserving
# an MCP session identifier.  Stateless mode keeps those requests compatible
# while leaving the local stdio/Claude mode unchanged.
mcp = FastMCP(
    "Trello MCP Server",
    stateless_http=True,
    json_response=True,
)

# Register tools
register_tools(mcp)


def _require_credentials() -> None:
    if not settings.api_key() or not settings.api_token():
        raise ValueError(
            "TRELLO_API_KEY and TRELLO_TOKEN must be set (process environment "
            f"or {settings.PACKAGE_ROOT / '.env'})"
        )


def _start_sync() -> None:
    """Kick off the background mirror sync, if the cache is enabled.

    Deliberately non-fatal: a sync that cannot start must not stop the server
    from serving whatever is already cached.
    """
    if not settings.cache_enabled():
        logger.info("Local cache disabled (TRELLO_CACHE_ENABLED=false)")
        return
    try:
        from server.cache.sync import start_background_sync

        start_background_sync()
        logger.info("Mirror database: %s", settings.db_path())
    except Exception:  # noqa: BLE001
        logger.exception("Could not start background sync; serving cached data only")


def start_claude_server():
    """Start the MCP server in stdio mode (Claude app, ChatGPT app, Codex)."""
    try:
        _require_credentials()

        logger.info("Starting Trello MCP Server in stdio mode...")
        _start_sync()
        mcp.run()
        logger.info("Trello MCP Server started successfully")
    except Exception as e:
        logger.error(f"Error starting stdio server: {str(e)}")
        raise


def start_sse_server():
    """Start the MCP server in Streamable HTTP mode using uvicorn."""
    # Imported here, not at module scope: stdio mode never needs a web server,
    # and a Docker image built for stdio should not fail at import if uvicorn
    # is absent.
    import uvicorn

    try:
        _require_credentials()
        _start_sync()

        host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_SERVER_PORT", "8000"))

        # FastMCP's current Streamable HTTP endpoint is /mcp.  Earlier
        # versions of this project documented /sse, and ChatGPT keeps the
        # endpoint URL with a saved connector.  Serve the same Streamable
        # protocol on both paths so a legacy registration continues to work
        # without falling back to a misleading expired-connection prompt.
        app = mcp.streamable_http_app()
        streamable_route = next(
            route
            for route in app.routes
            if getattr(route, "path", None) == mcp.settings.streamable_http_path
        )
        app.router.routes.append(Route("/sse", endpoint=streamable_route.endpoint))

        logger.info(
            f"Starting Trello MCP Server in HTTP mode on http://{host}:{port}..."
        )
        uvicorn.run(app, host=host, port=port)
    except Exception as e:
        logger.error(f"Error starting HTTP server: {str(e)}")
        raise


if __name__ == "__main__":
    try:
        # Check which mode to run in (default to true for Claude app mode)
        use_claude = os.getenv("USE_CLAUDE_APP", "true").lower() == "true"

        if use_claude:
            # Run in Claude app mode
            start_claude_server()
        else:
            # Run in SSE mode
            start_sse_server()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        raise
