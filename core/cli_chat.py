# =============================================================================
# core/cli_chat.py : CHAT + MCP RESOURCES AND PROMPTS
# =============================================================================
# CliChat extends Chat (core/chat.py) with two features that come from MCP:
#
#   @doc_id   -> uses an MCP RESOURCE. "What is in @plan.md?" makes the app read
#                docs://documents/plan.md and paste the text into the question, so
#                the LLM does not need a tool call to read it.
#   /command  -> uses an MCP PROMPT. "/summarize plan.md" asks the server for the
#                ready-made "summarize" prompt and uses its messages as the question.
#
# Remember who triggers what: tools = the LLM, resources = the app, prompts = the user.
# =============================================================================

from typing import List

from core.chat import Chat
from core.groq_service import GroqService
from mcp_client import MCPClient


class CliChat(Chat):  # `(Chat)` = inherits everything from Chat, then adds/overrides
    def __init__(
        self,
        doc_client: MCPClient,  # the built-in document server, used for resources and prompts
        clients: dict[str, MCPClient],  # all servers (their tools go to the LLM)
        llm_service: GroqService,
    ):
        super().__init__(clients=clients, llm_service=llm_service)  # run Chat's __init__ first
        self.doc_client: MCPClient = doc_client

    async def list_prompts(self):
        # MCP: ListPromptsRequest. Used by the UI to autocomplete /commands.
        return await self.doc_client.list_prompts()

    async def list_docs_ids(self) -> list[str]:
        # MCP: read the resource "docs://documents" -> a JSON list of document ids.
        return await self.doc_client.read_resource("docs://documents")

    async def get_doc_content(self, doc_id: str) -> str:
        # MCP: read the resource TEMPLATE "docs://documents/{doc_id}" -> one document's text.
        return await self.doc_client.read_resource(f"docs://documents/{doc_id}")

    async def get_prompt(self, command: str, doc_id: str):
        # MCP: GetPromptRequest. The server fills its template with doc_id and returns messages.
        return await self.doc_client.get_prompt(command, {"doc_id": doc_id})

    async def _extract_resources(self, query: str) -> str:
        # Find every word that starts with "@" and drop the "@":
        # "summarize @plan.md please" -> mentions == ["plan.md"]
        mentions = [word[1:] for word in query.split() if word.startswith("@")]

        # Only accept mentions that are real document ids on the server.
        doc_ids = await self.list_docs_ids()
        mentioned_docs: list[tuple[str, str]] = []

        for doc_id in doc_ids:
            if doc_id in mentions:
                content = await self.get_doc_content(doc_id)  # read the resource
                mentioned_docs.append((doc_id, content))

        # Wrap each document in <document id="..."> tags so the LLM can tell where
        # each one starts and ends.
        return "".join(
            f'\n<document id="{doc_id}">\n{content}\n</document>\n'
            for doc_id, content in mentioned_docs
        )

    async def _process_command(self, query: str) -> bool:
        # Returns True if the input was a /command (and handled), False otherwise.
        if not query.startswith("/"):
            return False

        words = query.split()
        command = words[0].replace("/", "")  # "/summarize" -> "summarize"

        if len(words) < 2:
            raise ValueError(f"Usage: /{command} <doc_id>")

        # Ask the MCP server for the prompt, convert its messages into our chat
        # format and add them to the history. The LLM will then follow the prompt
        # (for example "use the read_doc_contents tool, then summarize").
        messages = await self.get_prompt(command, words[1])
        self.messages += convert_prompt_messages_to_message_params(messages)
        return True

    async def _process_query(self, query: str):
        # Overrides Chat._process_query. 1) /command? handle it and stop.
        if await self._process_command(query):
            return

        # 2) Otherwise pull in any @mentioned documents (MCP resources) ...
        added_resources = await self._extract_resources(query)

        # 3) ... and build the final user message: the question plus the documents as context.
        prompt = f"""
        The user has a question:
        <query>
        {query}
        </query>

        The following context may be useful in answering their question:
        <context>
        {added_resources}
        </context>

        Note the user's query might contain references to documents like "@report.docx". The "@" is only
        included as a way of mentioning the doc. The actual name of the document would be "report.docx".
        If the document content is included in this prompt, you don't need to use an additional tool to read the document.
        Answer the user's question directly and concisely. Start with the exact information they need.
        Don't refer to or mention the provided context in any way - just use it to inform your answer.
        """

        self.messages.append({"role": "user", "content": prompt})


# ---- helpers: MCP prompt messages -> Groq/OpenAI chat messages --------------
def _text_of(content) -> str:
    """Extract text from an MCP prompt message content (object, dict, or list)."""
    # MCP content can arrive in different shapes depending on the library version,
    # so we handle a list, a dict and an object with .type/.text, and return "" for
    # anything else (images, etc.).
    if isinstance(content, list):
        return "\n".join(_text_of(c) for c in content)
    if isinstance(content, dict):
        return content.get("text", "") if content.get("type") == "text" else ""
    if getattr(content, "type", None) == "text":
        return getattr(content, "text", "")
    return ""


def convert_prompt_message_to_message_param(prompt_message) -> dict:
    # MCP prompt roles are "user" or "assistant", which already match the chat API.
    role = "user" if prompt_message.role == "user" else "assistant"
    return {"role": role, "content": _text_of(prompt_message.content)}


def convert_prompt_messages_to_message_params(prompt_messages: List) -> List[dict]:
    return [convert_prompt_message_to_message_param(m) for m in prompt_messages]
