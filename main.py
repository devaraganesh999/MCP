# =============================================================================
# main.py : ENTRY POINT of the app      (uv run main.py   |   python main.py)
# =============================================================================
# This file only does the WIRING. The real logic lives elsewhere:
#   1. read settings from .env
#   2. connect an MCP CLIENT to the MCP server(s). Two modes (chosen by MCP_SERVER_URL in .env):
#        - stdio (default): we START mcp_server.py ourselves as a child process
#        - HTTP: we CONNECT to a server you already started (e.g. in another terminal),
#          which mimics production where the server runs somewhere else
#   3. create the LLM service (Groq), the chat logic and the terminal UI
#   4. run the chat loop
#
# BIG PICTURE (this is the 12-step flow from the MCP client notes):
#   you type  ->  CliApp (core/cli.py)  ->  CliChat (core/cli_chat.py)  ->  Chat (core/chat.py)
#   Chat asks the LLM (core/groq_service.py)
#   LLM wants a tool -> ToolManager (core/tools.py) -> MCPClient (mcp_client.py)
#   -> MCP server (mcp_server.py) runs the tool -> result travels back up to the LLM
#
# PYTHON TERMS USED IN THIS FILE
#   sys.argv        List of command-line words. argv[0] is the script name,
#                   argv[1:] are extra arguments. `python main.py other.py` -> argv[1:] == ["other.py"].
#   sys.executable  Full path of the Python interpreter running this script. Used so the
#                   server starts with the SAME Python (same venv, same packages) as the app.
#   sys.platform    OS name: "win32" = Windows (also 64-bit), "linux", "darwin" = macOS.
#   __name__        Equals "__main__" only when this file is run directly, not when imported.
#   asyncio         Python's async framework. `async def` functions are run with `await`.
# =============================================================================

import asyncio
import sys
import os
from dotenv import load_dotenv  # reads a .env file and loads its KEY=VALUE lines as environment variables
from contextlib import AsyncExitStack  # helps manage SEVERAL async `with` blocks (explained in main())

from mcp_client import MCPClient  # our MCP client wrapper (mcp_client.py)
from core.groq_service import GroqService  # talks to the Groq LLM

from core.cli_chat import CliChat  # chat logic + @mentions + /commands
from core.cli import CliApp  # the terminal UI (autocomplete, input loop)

# Search for a `.env` file (starting from this file's folder) and copy its values
# into os.environ. Nothing happens if there is no .env file.
load_dotenv()

# Groq config. os.getenv("NAME", default) returns the environment variable, or the
# default if it is not set.
groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
groq_api_key = os.getenv("GROQ_API_KEY", "")
groq_reasoning_effort = os.getenv("GROQ_REASONING_EFFORT", "medium")

# `assert condition, "message"` stops the program immediately with that message if the
# condition is false. Here it gives a friendly error when .env is missing or incomplete.
# (We only CHECK the key here; the Groq library reads GROQ_API_KEY from the environment itself.)
assert groq_model, "Error: GROQ_MODEL cannot be empty. Update .env"
assert groq_api_key, "Error: GROQ_API_KEY cannot be empty. Update .env"


async def main():
    llm_service = GroqService(
        model=groq_model, reasoning_effort=groq_reasoning_effort
    )

    # Extra MCP servers can be passed on the command line:
    #   python main.py my_other_server.py
    # sys.argv[1:] drops the script name (main.py) and keeps only those extra scripts.
    server_scripts = sys.argv[1:]
    clients = {}  # name -> MCPClient, one entry per connected MCP server

    # USE_UV=1 in .env means "start servers with `uv run`"; anything else means
    # "start them with the Python that is running this app".
    use_uv = os.getenv("USE_UV", "0") == "1"

    def launcher(script: str) -> tuple[str, list[str]]:
        """How to start a server script: via `uv run`, or the current Python."""
        # Returns (command, arguments) for MCPClient, i.e. what to type to start the server:
        #   uv mode:      uv run mcp_server.py
        #   default mode: <sys.executable> mcp_server.py
        # sys.executable is the exact interpreter running this app, so the server gets
        # the same virtual environment and the same installed packages (fastmcp, etc.).
        # This works for both uv and pip users and on every OS.
        return ("uv", ["run", script]) if use_uv else (sys.executable, [script])

    # The built-in document server. The path is relative, so run the app from the
    # project folder (the child process starts in the same working directory).
    command, args = launcher("mcp_server.py")

    # ---- transport choice for the built-in document server ---------------------------
    # MCP_SERVER_URL empty/unset  -> stdio: launch mcp_server.py as a child process (above).
    # MCP_SERVER_URL set          -> HTTP : do NOT launch anything; connect to the running
    #                                server at that URL, e.g. http://127.0.0.1:8000/mcp
    #                                (start it first: fastmcp run mcp_server.py --transport http --port 8000)
    server_url = os.getenv("MCP_SERVER_URL", "")
    # Optional bearer token for servers that require authentication (HTTP only).
    # If set, every HTTP request carries the header:  Authorization: Bearer <token>
    # The server must be configured to check it; the local demo server does not.
    token = os.getenv("MCP_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else None

    # AsyncExitStack: normally you would nest one `async with MCPClient(...)` per server.
    # The stack lets us enter any NUMBER of clients (here in a loop) and guarantees that
    # when the block ends, or the app crashes, or you press Ctrl+C, every client is
    # closed in reverse order. That means no orphaned server processes are left behind.
    async with AsyncExitStack() as stack:
        # enter_async_context(x) is the same as `async with x as doc_client`:
        # it connects (stdio: starts the server subprocess; HTTP: opens the connection),
        # does the MCP handshake and returns the client.
        # `A if condition else B` picks the HTTP client when MCP_SERVER_URL is set.
        doc_client = await stack.enter_async_context(
            MCPClient(url=server_url, headers=headers)
            if server_url
            else MCPClient(command=command, args=args)
        )
        # This client is special: the CLI uses it for resources (@mentions) and prompts (/commands).
        clients["doc_client"] = doc_client

        # Connect to every extra server script given on the command line.
        # Only their TOOLS are offered to the LLM (see core/tools.py).
        # Extra servers are always started with stdio (as child processes), even when
        # MCP_SERVER_URL switches the document server to HTTP.
        for i, server_script in enumerate(server_scripts):
            client_id = f"client_{i}_{server_script}"  # unique key, e.g. "client_0_my_server.py"
            cmd, cmd_args = launcher(server_script)
            client = await stack.enter_async_context(
                MCPClient(command=cmd, args=cmd_args)
            )
            clients[client_id] = client

        # Build the layers from the bottom up and hand each one what it needs.
        chat = CliChat(
            doc_client=doc_client,
            clients=clients,
            llm_service=llm_service,
        )

        cli = CliApp(chat)
        await cli.initialize()  # fetch document ids and prompts from the server for autocomplete
        await cli.run()  # the input loop; returns when you press Ctrl+C or Ctrl+D


if __name__ == "__main__":
    # sys.platform == "win32" is true on Windows (the name is historical: it is "win32"
    # on 64-bit Windows too). Other values: "linux", "darwin" (macOS).
    # On Windows, asyncio needs the "Proactor" event loop, the only kind that can start
    # subprocesses, and each stdio MCP server we launch IS a subprocess. Python 3.8+ already
    # uses it by default on Windows, so this is a safety net. (Python 3.14+ deprecates
    # the asyncio "policy" API, so a DeprecationWarning may appear; it is harmless.)
    # On Linux/macOS this block is skipped.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    # Start the event loop and run main() until it finishes.
    asyncio.run(main())
