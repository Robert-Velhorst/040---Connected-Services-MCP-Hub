import logging
import os

import uvicorn
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from starlette.routing import Route

from server.tools.tools import register_tools

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
# Trello credentials are carried in query parameters. Keep HTTP client request
# logs below INFO so those URLs cannot leak into normal server logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpx2").setLevel(logging.WARNING)
logging.getLogger("httpcore2").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


# Initialize MCP server
# ChatGPT can make independent Streamable HTTP requests instead of preserving
# an MCP session identifier.  Stateless mode keeps those requests compatible
# while leaving the local stdio/Claude mode unchanged.
mcp = MCPServer("Trello MCP Server")

# Register tools
register_tools(mcp)


def start_claude_server():
    """Start the MCP server in Claude app mode"""
    try:
        # Verify environment variables
        if not os.getenv("TRELLO_API_KEY") or not os.getenv("TRELLO_TOKEN"):
            raise ValueError(
                "TRELLO_API_KEY and TRELLO_TOKEN must be set in environment variables"
            )

        logger.info("Starting Trello MCP Server in Claude app mode...")
        mcp.run()
        logger.info("Trello MCP Server started successfully")
    except Exception as e:
        logger.error(f"Error starting Claude server: {str(e)}")
        raise


def start_sse_server():
    """Start the MCP server in Streamable HTTP mode using uvicorn."""
    try:
        # Verify environment variables
        if not os.getenv("TRELLO_API_KEY") or not os.getenv("TRELLO_TOKEN"):
            raise ValueError(
                "TRELLO_API_KEY and TRELLO_TOKEN must be set in environment variables"
            )

        host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_SERVER_PORT", "8000"))

        # MCPServer's current Streamable HTTP endpoint is /mcp.  Earlier
        # versions of this project documented /sse, and ChatGPT keeps the
        # endpoint URL with a saved connector.  Serve the same Streamable
        # protocol on both paths so a legacy registration continues to work
        # without falling back to a misleading expired-connection prompt.
        app = mcp.streamable_http_app(
            streamable_http_path="/mcp",
            json_response=True,
            stateless_http=True,
            host=host,
        )
        streamable_route = next(
            route
            for route in app.routes
            if getattr(route, "path", None) == "/mcp"
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
