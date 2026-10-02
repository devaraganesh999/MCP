# =============================================================================
# core/chat.py : THE CHAT LOOP (the "agent loop")
# =============================================================================
# This is where the LLM and MCP meet. The idea is a simple loop:
#
#     ask the LLM  ->  does it want a tool?
#          yes: run the tool through MCP, give the result back, ask the LLM again
#          no : it has its final answer, return it
#
# That loop is steps 5-11 of the 12-step flow from the MCP client notes.
# =============================================================================

from core.groq_service import GroqService  # the LLM wrapper
from mcp_client import MCPClient  # the MCP client wrapper
from core.tools import ToolManager  # lists MCP tools and runs tool calls


class Chat:
    def __init__(self, llm_service: GroqService, clients: dict[str, MCPClient]):
        self.llm_service: GroqService = llm_service
        self.clients: dict[str, MCPClient] = clients  # every connected MCP server
        # The conversation history. The LLM has no memory, so we send the WHOLE
        # list on every request. Each item looks like {"role": "user", "content": "..."}.
        self.messages: list[dict] = []

    async def _process_query(self, query: str):
        # Basic version: just store the user's text. The subclass CliChat overrides
        # this to add @document context and to handle /commands.
        self.messages.append({"role": "user", "content": query})

    async def run(self, query: str) -> str:
        await self._process_query(query)  # step 1: the user's question enters the history

        while True:
            # Steps 2-5: collect the tools from all MCP servers (ListToolsRequest happens
            # inside ToolManager) and send history + tools to the LLM.
            # (Tools are re-fetched on every pass of the loop; fine for a small demo,
            # but a bigger app might cache them.)
            choice = await self.llm_service.chat(
                messages=self.messages,
                tools=await ToolManager.get_all_tools(self.clients),
            )
            message = choice.message  # the LLM's reply (text and/or tool requests)

            # Keep the LLM's reply in the history. If it asked for tools, this
            # message records WHICH tools, which the API requires to see before the results.
            self.llm_service.add_assistant_message(self.messages, message)

            # Step 6: finish_reason tells us WHY the LLM stopped.
            #   "tool_calls" = it wants us to run one or more tools first
            #   "stop"       = it finished and message.content is the answer
            if choice.finish_reason == "tool_calls" and message.tool_calls:
                # The LLM sometimes writes a short text before calling tools; show it.
                text = self.llm_service.text_from_message(message)
                if text:
                    print(text)
                # Steps 7-9: run each requested tool through the MCP client
                # (CallToolRequest -> MCP server -> result).
                tool_results = await ToolManager.execute_tool_requests(
                    self.clients, message
                )
                # Step 10: put the tool results in the history, then loop back so the
                # LLM can read them and either call more tools or answer.
                self.llm_service.add_tool_results(self.messages, tool_results)
            else:
                # Steps 11-12: no tools needed, so this text is the final answer.
                return self.llm_service.text_from_message(message)
