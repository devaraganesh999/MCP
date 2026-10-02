# =============================================================================
# core/tools.py : THE BRIDGE BETWEEN THE LLM AND MCP TOOLS
# =============================================================================
# ToolManager does two jobs:
#   1. get_all_tools()          ask every MCP server "what tools do you have?"
#                               (ListToolsRequest) and combine the answers
#   2. execute_tool_requests()  when the LLM asks to use a tool, find the MCP server
#                               that owns it and run it (CallToolRequest)
# =============================================================================

import json
from typing import Optional

from mcp_client import MCPClient


class ToolManager:
    # @classmethod: these methods belong to the class itself, so we call
    # ToolManager.get_all_tools(...) without creating an object first.
    @classmethod
    async def get_all_tools(cls, clients: dict[str, MCPClient]) -> list[dict]:
        """Gets all tools from the provided clients (provider-neutral format)."""
        tools = []
        # One MCP client per server. Loop over all of them so tools from several
        # servers are offered to the LLM together.
        for client in clients.values():
            # client.list_tools() sends the MCP ListToolsRequest to that server.
            for t in await client.list_tools():
                # Convert each MCP Tool object into a plain dict with 3 fields:
                #   name          what the LLM will call
                #   description   when/why to use it
                #   input_schema  JSON schema describing the arguments
                # core/groq_service.py later reshapes this dict for the Groq API.
                tools.append(
                    {
                        "name": t.name,
                        "description": t.description,
                        "input_schema": t.input_schema,
                    }
                )
        return tools

    @classmethod
    async def _find_client_with_tool(
        cls, clients: list[MCPClient], tool_name: str
    ) -> Optional[MCPClient]:
        """Finds the first client that has the specified tool."""
        # The LLM only gives us a tool NAME. With several MCP servers connected we must
        # work out which one provides it, so we ask each server for its tool list.
        # If two servers share a tool name, the first one found wins.
        for client in clients:
            tools = await client.list_tools()
            if any(t.name == tool_name for t in tools):
                return client
        return None  # no server has it

    @classmethod
    def _build_tool_result_message(cls, tool_call_id: str, text: str) -> dict:
        """Groq/OpenAI-style tool result message."""
        # role "tool" marks this as a tool's output. tool_call_id links the result to
        # the exact request the LLM made (the LLM may request several tools at once).
        return {"role": "tool", "tool_call_id": tool_call_id, "content": text}

    @classmethod
    async def execute_tool_requests(
        cls, clients: dict[str, MCPClient], message
    ) -> list[dict]:
        """Executes every tool call on an assistant message and returns tool messages."""
        results: list[dict] = []

        # message.tool_calls is the list of tools the LLM asked for ("or []" covers None).
        for tool_call in message.tool_calls or []:
            tool_name = tool_call.function.name

            # The LLM sends the arguments as a JSON TEXT string, e.g. '{"doc_id": "plan.md"}'.
            # json.loads turns it into a Python dict. If the model produced broken JSON,
            # we report the problem back to it instead of crashing.
            try:
                tool_input = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError as e:
                results.append(
                    cls._build_tool_result_message(
                        tool_call.id, f"Error: invalid tool arguments: {e}"
                    )
                )
                continue  # skip to the next tool call

            # Which MCP server owns this tool?
            client = await cls._find_client_with_tool(
                list(clients.values()), tool_name
            )
            if not client:
                results.append(
                    cls._build_tool_result_message(
                        tool_call.id, "Error: could not find that tool"
                    )
                )
                continue

            try:
                # client.call_tool sends the MCP CallToolRequest to the server.
                # `output` is a CallToolResult: output.content is a list of content
                # blocks and output.is_error says whether the tool failed.
                output = await client.call_tool(tool_name, tool_input)
                # Join the text of every text block into one string for the LLM.
                # (Blocks without .text, such as images, are skipped.)
                text = "\n".join(
                    item.text
                    for item in output.content
                    if getattr(item, "text", None) is not None
                )
                if output.is_error:
                    # The server reported a failure (e.g. ToolError "Doc ... not found").
                    # Prefix with "Error:" so the LLM knows it failed and can adapt.
                    text = f"Error: {text}"
            except Exception as e:
                # Something went wrong talking to the server (not a tool failure).
                # Report it to the LLM and print it for the developer.
                text = f"Error executing tool '{tool_name}': {e}"
                print(text)

            results.append(cls._build_tool_result_message(tool_call.id, text))

        return results
