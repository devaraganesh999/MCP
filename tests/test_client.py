# =============================================================================
# tests/test_client.py : TEST THE MCP CLIENT (offline, no API key, no LLM)
# =============================================================================
# WHAT DOES THIS TEST?
#   Our MCPClient wrapper (mcp_client.py) talking to the real mcp_server.py over stdio.
#   It exercises every client method once:
#       list_tools / call_tool / read_resource / list_prompts / get_prompt
#   and checks both the happy path and the error path.
#
# TWO MODES (chosen by the MCP_SERVER_URL environment variable):
#   stdio (default): the test starts its own server. Each run gets a FRESH server.
#   HTTP           : the test connects to a server YOU started (README section 4b).
#
# HOW TO RUN (from the project folder):
#   stdio:
#       uv:   uv run python tests/test_client.py
#       pip:  python tests/test_client.py          (venv activated)
#   HTTP (start the server first in another terminal:
#         fastmcp run mcp_server.py --transport http --port 8000):
#       macOS/Linux:  MCP_SERVER_URL=http://127.0.0.1:8000/mcp python tests/test_client.py
#       PowerShell :  $env:MCP_SERVER_URL="http://127.0.0.1:8000/mcp"; python tests/test_client.py
#       (prefix with `uv run` for uv: uv run python tests/test_client.py)
#   Expected last line:  ALL CLIENT TESTS PASSED
#
# An HTTP server keeps running between tests, so the edit made below is UNDONE
# at the end of the check. Otherwise the second run would fail.
# =============================================================================

import asyncio
import os
import sys
from pathlib import Path

# This file lives in tests/, but `import mcp_client` needs the PROJECT folder on
# Python's search path. __file__ is this file's path; .parent.parent = project folder.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp_client import MCPClient  # noqa: E402  (import placed after the path tweak on purpose)

# Absolute path to the server, so the test works no matter which folder you run it from.
SERVER = str(ROOT / "mcp_server.py")

failures: list[str] = []


def check(name: str, condition: bool, detail: str = ""):
    """Print PASS/FAIL for one check and remember failures."""
    print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def text_of(result) -> str:
    """Join the text blocks of a CallToolResult into one string."""
    return "\n".join(getattr(c, "text", "") or "" for c in result.content)


async def main():
    # MCP_SERVER_URL set -> HTTP (connect to a running server); empty -> stdio (start our own).
    url = os.getenv("MCP_SERVER_URL", "")
    print(f"transport: {'HTTP ' + url if url else 'stdio (starts its own server)'}")
    # sys.executable = the Python running THIS test, so (in stdio mode) the server starts
    # with the same virtual environment and packages (works for both uv and pip).
    async with (
        MCPClient(url=url) if url else MCPClient(command=sys.executable, args=[SERVER])
    ) as client:
        print("tools (ListToolsRequest)")
        tools = await client.list_tools()
        names = {t.name for t in tools}
        check("server exposes read_doc_contents and edit_document", names == {"read_doc_contents", "edit_document"}, str(names))
        read_tool = next(t for t in tools if t.name == "read_doc_contents")
        check("tool schema requires doc_id", read_tool.input_schema.get("required") == ["doc_id"])

        print("call_tool (CallToolRequest)")
        ok = await client.call_tool("read_doc_contents", {"doc_id": "plan.md"})
        check("read existing doc: no error", ok.is_error is False)
        check("read existing doc: correct text", "implementation" in text_of(ok), text_of(ok))

        bad = await client.call_tool("read_doc_contents", {"doc_id": "nope"})
        check("unknown doc: is_error is True (no Python exception)", bad.is_error is True)
        check("unknown doc: error text comes back", "not found" in text_of(bad), text_of(bad))

        edit = await client.call_tool(
            "edit_document", {"doc_id": "plan.md", "old_str": "steps", "new_str": "STEPS"}
        )
        check("edit_document succeeds", edit.is_error is False and "updated" in text_of(edit), text_of(edit))
        reread = await client.call_tool("read_doc_contents", {"doc_id": "plan.md"})
        check("edit is visible when read back", "STEPS" in text_of(reread), text_of(reread))

        # Undo the edit. A stdio server dies after the test, but an HTTP server keeps running,
        # so without this undo the second run would fail ("steps" would already be "STEPS").
        undo = await client.call_tool(
            "edit_document", {"doc_id": "plan.md", "old_str": "STEPS", "new_str": "steps"}
        )
        check("edit can be undone (keeps HTTP reruns clean)", undo.is_error is False, text_of(undo))

        missing = await client.call_tool(
            "edit_document", {"doc_id": "plan.md", "old_str": "zzz-not-there", "new_str": "x"}
        )
        check("edit with text that is not in the doc -> error", missing.is_error is True)

        print("read_resource (ReadResourceRequest)")
        ids = await client.read_resource("docs://documents")
        check("docs://documents returns a Python list of 6 ids", isinstance(ids, list) and len(ids) == 6, str(ids))
        body = await client.read_resource("docs://documents/spec.txt")
        check("resource template returns the document text", isinstance(body, str) and "technical requirements" in body, str(body))

        print("prompts (ListPromptsRequest / GetPromptRequest)")
        prompts = await client.list_prompts()
        check("prompts are format and summarize", {p.name for p in prompts} == {"format", "summarize"})
        messages = await client.get_prompt("summarize", {"doc_id": "report.pdf"})
        first = messages[0]
        check("prompt message has role user", first.role == "user")
        check("prompt text contains the doc id we passed", "report.pdf" in getattr(first.content, "text", ""))

    print()
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED: {failures}")
        sys.exit(1)  # non-zero exit code = failure (useful in CI)
    print("ALL CLIENT TESTS PASSED")


if __name__ == "__main__":
    # On Windows asyncio needs the Proactor loop to start the server subprocess.
    # sys.platform is "win32" on Windows (including 64-bit); see main.py for details.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
