# =============================================================================
# mcp_server.py : THE MCP SERVER
# =============================================================================
# WHAT IS AN MCP SERVER?
#   A small program that wraps some data or functionality (here: a few in-memory
#   documents) and exposes it to AI apps in a standard way, so the app does not
#   need custom integration code. Any MCP client can talk to it.
#
# WHAT CAN A SERVER EXPOSE? Three kinds of things. The difference is WHO decides
# when each one gets used:
#
#   | Kind      | Who triggers it?            | In this file                       |
#   |-----------|-----------------------------|------------------------------------|
#   | TOOL      | The MODEL (Claude/Groq)     | read_doc_contents, edit_document   |
#   | RESOURCE  | The APP (our Python code)   | docs://documents, docs://documents/{doc_id} |
#   | PROMPT    | The USER (slash commands)   | /format, /summarize                |
#
#   - Tool     = an action. The LLM sees its name + description + argument schema
#                and decides on its own when to call it.
#   - Resource = read-only data identified by a URI (like a URL). Our app fetches
#                it directly (for example when you type @plan.md).
#   - Prompt   = a reusable, parameterised message template that the user picks.
#
# HOW DOES THIS SERVER TALK TO THE CLIENT? (the "transport")
#   By default this app uses STDIO: the client starts this file as a child
#   process and they exchange JSON messages through the child's stdin/stdout.
#   IMPORTANT consequence: never print() to stdout in a stdio server, because
#   that text would be mixed into the protocol messages and break them. That is
#   why we silence the startup banner and lower the log level at the bottom.
#
# HOW DO I RUN / TEST IT ON ITS OWN? (no LLM, no API key needed)
#   uv:   uv run fastmcp run mcp_server.py        pip:  fastmcp run mcp_server.py
#   Inspector: see README section 5.   fastmcp CLI: see README section 6.
# =============================================================================

import json
from typing import Annotated

from pydantic import Field  # Pydantic: lets us attach a human-readable description to each argument
from fastmcp import FastMCP  # FastMCP: the library that turns plain Python functions into MCP tools/resources/prompts
from fastmcp.exceptions import ToolError, ResourceError  # special errors whose message is passed back to the caller
from fastmcp.prompts import Message  # helper to build the chat messages a prompt returns

# Create the server object. "DocumentMCP" is just the server's display name.
# Every @mcp.tool / @mcp.resource / @mcp.prompt below registers itself on THIS object.
mcp = FastMCP("DocumentMCP")

# Our "database": a plain dictionary kept in memory.
#   key   = document id (we call it doc_id)
#   value = the document's text
# Because it lives only in memory, edits are lost when the server restarts.
docs = {
    "deposition.md": "This deposition covers the testimony of Angela Smith, P.E.",
    "report.pdf": "The report details the state of a 20m condenser tower.",
    "financials.docx": "These financials outline the project's budget and expenditures.",
    "outlook.pdf": "This document presents the projected future performance of the system.",
    "plan.md": "The plan outlines the steps for the project's implementation.",
    "spec.txt": "These specifications define the technical requirements for the equipment.",
}


# ---------------------------------------------------------------- tools
# A TOOL is a Python function the LLM is allowed to call.
# The @mcp.tool decorator registers the function and AUTOMATICALLY builds the
# JSON schema the LLM needs, using:
#   - name=         the tool name the LLM sees (does not have to match the Python name)
#   - description=  tells the LLM WHAT the tool does and WHEN to use it
#   - type hints    (doc_id: str) -> the argument types
#   - Field(...)    -> the description of each argument
#
# For read_doc_contents the generated schema looks like this (you never write it):
#   {"type": "object",
#    "properties": {"doc_id": {"type": "string", "description": "Id of the document to read"}},
#    "required": ["doc_id"]}
@mcp.tool(
    name="read_doc_contents",
    description="Read the contents of a document and return it as a string.",
)
def read_document(
    # Annotated[str, Field(...)] means: "this argument is a string, and here is its description".
    doc_id: Annotated[str, Field(description="Id of the document to read")],
) -> str:
    if doc_id not in docs:
        # ToolError: the message is sent back to the caller (and then to the LLM),
        # so the LLM can read "not found" and recover, e.g. by trying another id.
        # Other exception types may have their details hidden, depending on server settings.
        raise ToolError(f"Doc with id {doc_id} not found")
    # Whatever the function returns becomes the tool result (text content).
    return docs[doc_id]


@mcp.tool(
    name="edit_document",
    description="Edit a document by replacing a string in the document's content with a new string.",
)
def edit_document(
    doc_id: Annotated[str, Field(description="Id of the document that will be edited")],
    old_str: Annotated[
        str,
        Field(description="The text to replace. Must match exactly, including whitespace"),
    ],
    new_str: Annotated[
        str, Field(description="The new text to insert in place of the old text")
    ],
) -> str:
    # Guard 1: the document must exist.
    if doc_id not in docs:
        raise ToolError(f"Doc with id {doc_id} not found")
    # Guard 2: the text to replace must actually be in the document, otherwise
    # .replace() would silently do nothing and the LLM would think the edit worked.
    if old_str not in docs[doc_id]:
        raise ToolError(f"Text to replace was not found in {doc_id}")

    # Plain Python find-and-replace on the in-memory document.
    docs[doc_id] = docs[doc_id].replace(old_str, new_str)
    # Returning a confirmation message lets the LLM know the edit succeeded.
    return f"Document {doc_id} updated successfully"


# ------------------------------------------------------------ resources
# A RESOURCE is read-only data addressed by a URI (like a web address).
# "docs://..." is a custom scheme we invented; the client asks for a URI and the
# server returns the content. Resources are chosen by the APP, not by the LLM:
# here, the CLI uses them to autocomplete @mentions and to inject a document's
# text into your question.
#
# This is a DIRECT resource (fixed URI). mime_type tells the client how to
# interpret the text; mcp_client.py parses "application/json" into a Python list.
@mcp.resource("docs://documents", mime_type="application/json")
def list_docs() -> str:
    """All document ids."""  # a docstring becomes the resource's description
    return json.dumps(list(docs.keys()))  # a JSON string like '["deposition.md", ...]'


# This is a RESOURCE TEMPLATE: the {doc_id} part of the URI is a placeholder.
# Asking for "docs://documents/plan.md" calls fetch_doc(doc_id="plan.md").
# The placeholder name in the URI must match the function argument name.
@mcp.resource("docs://documents/{doc_id}", mime_type="text/plain")
def fetch_doc(doc_id: str) -> str:
    """Contents of a single document."""
    if doc_id not in docs:
        # ResourceError is the resource-side twin of ToolError.
        raise ResourceError(f"Doc with id {doc_id} not found")
    return docs[doc_id]


# --------------------------------------------------------------- prompts
# A PROMPT is a reusable message template that the USER picks (in our CLI they
# type /format report.pdf). The server fills in the template and returns ready
# made chat messages; the app then sends them to the LLM.
# Notice the prompt itself does no work: it just tells the LLM which tool to use.
@mcp.prompt(
    name="format",
    description="Rewrites the contents of the document in Markdown format.",
)
def format_document(
    doc_id: Annotated[str, Field(description="Id of the document to format")],
) -> list[Message]:
    # f-string: {doc_id} is replaced with the real id when the prompt is requested.
    prompt = f"""
    Your goal is to reformat a document to be written with markdown syntax.

    The id of the document you need to reformat is:
    <document_id>
    {doc_id}
    </document_id>

    Add in headers, bullet points, tables, etc as necessary. Feel free to add in extra text, but don't change the meaning of the report.
    Use the 'edit_document' tool to edit the document. After the document has been edited, respond with the final version of the doc. Don't explain your changes.
    """
    # Message(text) builds one chat message (role "user" by default).
    # A prompt returns a LIST of messages, so it could also include assistant turns.
    return [Message(prompt)]


@mcp.prompt(
    name="summarize",
    description="Summarizes the contents of a document.",
)
def summarize_document(
    doc_id: Annotated[str, Field(description="Id of the document to summarize")],
) -> list[Message]:
    prompt = f"""
    Your goal is to summarize the contents of a document.

    The id of the document you need to summarize is:
    <document_id>
    {doc_id}
    </document_id>

    Use the 'read_doc_contents' tool to read the document, then reply with a short, clear summary.
    """
    return [Message(prompt)]


# `__name__` is "__main__" only when this file is run directly
# (python mcp_server.py / uv run mcp_server.py). It is NOT "__main__" when the
# file is imported by another module, so importing it will not start the server.
# (`fastmcp run mcp_server.py` also loads the file and finds the `mcp` object
# itself, then picks the transport from its command-line flags.)
if __name__ == "__main__":
    # transport="stdio"  : talk through stdin/stdout (what mcp_client.py expects).
    # show_banner=False  : do not print FastMCP's startup banner (keeps the console clean).
    # log_level="ERROR"  : only log real errors. Chatty logs would be noise in the
    #                      client's terminal, because this process is its child.
    mcp.run(transport="stdio", show_banner=False, log_level="ERROR")
