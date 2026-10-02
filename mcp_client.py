# =============================================================================
# mcp_client.py : THE MCP CLIENT
# =============================================================================
# WHAT IS AN MCP CLIENT?
#   The bridge between YOUR app and an MCP server. Your app says "list the tools"
#   or "call this tool", and the client handles the protocol details: connecting to
#   the server, sending the messages, receiving and decoding the replies.
#
# TWO WAYS TO CONNECT (the "transport"). The rest of the app does not care which:
#
#   | Mode  | You pass to MCPClient      | Who starts the server?    | Typical use |
#   |-------|----------------------------|---------------------------|-------------|
#   | stdio | command=..., args=[...]    | THIS client (child process)| local dev   |
#   | HTTP  | url="http://host:port/mcp" | YOU, separately (already running) | production-like |
#
#   main.py picks the mode: if MCP_SERVER_URL is set in .env it uses HTTP,
#   otherwise stdio.
#
# This class is a thin wrapper around fastmcp.Client. We wrap it so the rest of
# the app only sees a few simple methods. Each method maps to one MCP message:
#
#   | Our method       | MCP request it sends        | What it returns            |
#   |------------------|-----------------------------|----------------------------|
#   | list_tools()     | ListToolsRequest            | the server's tools         |
#   | call_tool()      | CallToolRequest             | the tool's result          |
#   | list_prompts()   | ListPromptsRequest          | the server's prompts       |
#   | get_prompt()     | GetPromptRequest            | messages for one prompt    |
#   | read_resource()  | ReadResourceRequest         | the content of a URI       |
#
# LIFECYCLE (what happens under the hood):
#   1. connect()  -> stdio: the client starts the server as a CHILD PROCESS
#                    (e.g. "python mcp_server.py").
#                    HTTP : nothing is started; the client just connects to the URL.
#                    Either way it then sends an "initialize" handshake so both
#                    sides agree on protocol version/features.
#   2. we send requests; the server sends results back
#                    stdio: JSON messages over the child's stdin/stdout
#                    HTTP : JSON messages in HTTP POST requests to the /mcp URL
#   3. cleanup()  -> the connection is closed. In stdio mode the child process is
#                    ours to stop; in HTTP mode the server keeps running.
#
# HOW DO I TEST THIS FILE?
#   Quick smoke test (see main() at the bottom), stdio:
#       uv:   uv run mcp_client.py        pip:  python mcp_client.py
#   Same smoke test over HTTP (start the server first, see README section 4b):
#       set MCP_SERVER_URL=http://127.0.0.1:8000/mcp   then run the same command
#   Fuller test:  tests/test_client.py   (see README section 7)
# =============================================================================

import os  # to read the MCP_SERVER_URL environment variable in the smoke test
import sys  # access to interpreter info: sys.executable, sys.platform (explained below)
import json  # to decode JSON text returned by resources
import asyncio  # Python's async framework; MCP calls are `async` (they wait for I/O)
from typing import Optional, Any

from fastmcp import Client  # the real MCP client implementation
from fastmcp.client.transports import (
    StdioTransport,  # stdio: "launch a child process and talk via its stdin/stdout"
    StreamableHttpTransport,  # HTTP: "connect to a server that is already running at a URL"
)


class MCPClient:
    """Thin wrapper around fastmcp.Client. Talks to a server over stdio OR HTTP."""

    def __init__(
        self,
        # ---- stdio mode: we start the server ourselves --------------------
        command: Optional[str] = None,  # the program to start, e.g. the path to python, or "uv"
        args: Optional[list[str]] = None,  # its arguments, e.g. ["mcp_server.py"] or ["run", "mcp_server.py"]
        env: Optional[dict] = None,  # optional extra environment variables for the child process
        # ---- HTTP mode: the server is already running ---------------------
        url: Optional[str] = None,  # e.g. "http://127.0.0.1:8000/mcp" (note the /mcp path)
        headers: Optional[dict] = None,  # extra HTTP headers, e.g. {"Authorization": "Bearer <token>"}
    ):
        # Rule: if a `url` is given we use HTTP, otherwise we use stdio.
        # Nothing is connected yet in either case; the connection is made later in
        # connect()/__aenter__ below.
        if url:
            # HTTP ("streamable HTTP"): the server is ALREADY running somewhere (another
            # terminal, container or machine). We only need its address. `headers` is the
            # place for credentials, which a production server will usually require.
            self._client = Client(StreamableHttpTransport(url=url, headers=headers))
        else:
            # stdio: StdioTransport = "launch `command args...` as a subprocess and speak
            # MCP through its stdin/stdout". `args or []` avoids passing None if the
            # caller forgot args. Note: `command` is required in this mode.
            self._client = Client(
                StdioTransport(command=command, args=args or [], env=env)
            )

    async def connect(self):
        # __aenter__ is what `async with client:` calls first.
        #   stdio: it starts the server subprocess.
        #   HTTP : it opens the connection to the URL (the server must already be running,
        #          otherwise you get "Client failed to connect").
        # Then it performs the MCP "initialize" handshake.
        await self._client.__aenter__()

    async def list_tools(self):
        # ListToolsRequest: "what tools do you provide?"
        # Returns a list of Tool objects. Each has .name, .description and
        # .input_schema (the JSON schema of its arguments). The LLM needs exactly
        # this information to decide which tool to call.
        return await self._client.list_tools()

    async def call_tool(self, tool_name: str, tool_input: dict):
        # CallToolRequest: "run this tool with these arguments".
        # tool_input is a dict like {"doc_id": "plan.md"}.
        #
        # raise_on_error=False -> if the tool fails (for example the server raised
        # ToolError("Doc ... not found")), we do NOT get a Python exception.
        # Instead we get a normal result whose `.is_error` is True and whose
        # `.content` holds the error text. That lets us pass the error to the LLM
        # so it can react, instead of crashing the whole chat.
        #
        # The result (CallToolResult) has:
        #   .content   list of content blocks (usually TextContent with a .text field)
        #   .is_error  True/False
        return await self._client.call_tool(
            tool_name, tool_input, raise_on_error=False
        )

    async def list_prompts(self):
        # ListPromptsRequest: "which prompt templates do you have?"
        # (this app: "format" and "summarize")
        return await self._client.list_prompts()

    async def get_prompt(self, prompt_name: str, args: dict[str, str]):
        # GetPromptRequest: "fill in prompt <name> with these arguments".
        # args example: {"doc_id": "plan.md"}.
        result = await self._client.get_prompt(prompt_name, args)
        # The result wraps a list of chat messages (role + content). We return just
        # the list because that is all the app needs.
        return result.messages

    async def read_resource(self, uri: str) -> Any:
        # ReadResourceRequest: "give me the content stored at this URI",
        # e.g. "docs://documents" or "docs://documents/plan.md".
        # The server answers with a LIST of content items (a resource may have
        # several parts); ours always has exactly one, so we take the first.
        contents = await self._client.read_resource(uri)
        resource = contents[0]
        # Text resources have a .text field. Binary resources carry a .blob instead,
        # which we do not need here, so we return None for those.
        text = getattr(resource, "text", None)
        if text is None:
            return None
        # The server marked "docs://documents" as application/json, so we decode it
        # into a real Python list. Plain text (like a document body) is returned as is.
        if resource.mime_type == "application/json":
            return json.loads(text)
        return text

    async def cleanup(self):
        # __aexit__ is what `async with` calls at the end. It closes the connection.
        # The three None arguments mean "no exception happened" (the standard
        # exc_type, exc_value, traceback triple).
        # Note (stdio only): by default fastmcp keeps the server subprocess alive after
        # the connection closes (keep_alive=True) so it could be reused; it is shut
        # down when the Python program ends. In HTTP mode there is no subprocess:
        # the server keeps running on its own, as it should.
        await self._client.__aexit__(None, None, None)

    # ---- async context manager support -------------------------------------
    # These two methods let us write:
    #       async with MCPClient(...) as client:
    #           ...use client...
    # and be sure the connection is cleaned up even if an error happens inside.
    # (`async with` is the async version of `with open(file) as f:`.)
    async def __aenter__(self):
        await self.connect()
        return self  # this is the `client` in `as client`

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()


# ---------------------------------------------------------------------------
# SMOKE TEST: run this file directly to check that client and server work together.
#   stdio:  uv run mcp_client.py            |  pip (venv active):  python mcp_client.py
#   HTTP :  start the server first (README 4b), then set MCP_SERVER_URL and run the same command:
#             macOS/Linux:  MCP_SERVER_URL=http://127.0.0.1:8000/mcp python mcp_client.py
#             PowerShell :  $env:MCP_SERVER_URL="http://127.0.0.1:8000/mcp"; python mcp_client.py
# In stdio mode run it from the project folder, because "mcp_server.py" below is a relative path.
# Expected output:
#   transport: stdio (starts its own server)      <- or: transport: HTTP http://127.0.0.1:8000/mcp
#   tools: ['read_doc_contents', 'edit_document']
#   docs: ['deposition.md', 'report.pdf', 'financials.docx', ...]
# ---------------------------------------------------------------------------
async def main():
    # os.getenv("NAME", "") returns the environment variable's value, or "" if it is not set.
    url = os.getenv("MCP_SERVER_URL", "")
    if url:
        # HTTP mode: nothing is launched; we connect to the running server.
        print(f"transport: HTTP {url}")
        client_cm = MCPClient(url=url)
    else:
        print("transport: stdio (starts its own server)")
        client_cm = MCPClient(
            # sys.executable = the full path of the Python interpreter that is running
            # THIS script (for example /project/.venv/bin/python).
            # Why not just write "python"? The word "python" is looked up on your PATH
            # and might be a DIFFERENT Python (system Python, another venv) that does
            # not have fastmcp installed. sys.executable guarantees the server starts
            # with the same interpreter and the same installed packages as the client.
            # It works the same for uv and pip, and on Windows, macOS and Linux.
            command=sys.executable, args=["mcp_server.py"]
        )
    async with client_cm as client:
        print("tools:", [t.name for t in await client.list_tools()])
        print("docs:", await client.read_resource("docs://documents"))


if __name__ == "__main__":
    # sys.platform names the operating system:
    #   "win32"  = Windows (even 64-bit; the name is historical)
    #   "linux"  = Linux        "darwin" = macOS
    # On Windows, asyncio must use the "Proactor" event loop, the only kind that can
    # launch subprocesses, and our stdio server IS a subprocess. Python 3.8+ already
    # uses it by default on Windows, so this is a safety net. (Python 3.14+ marks
    # the asyncio "policy" API as deprecated, so you may see a DeprecationWarning
    # there; it is harmless.) On Linux/macOS this block is skipped.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    # asyncio.run starts the event loop, runs main() until it finishes, then closes the loop.
    asyncio.run(main())
