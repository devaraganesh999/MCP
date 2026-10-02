# =============================================================================
# core/groq_service.py : THE LLM WRAPPER (Groq)
# =============================================================================
# This file is the ONLY place that knows about the LLM provider. MCP does not care
# which LLM you use; it just supplies tools. To switch to another provider you would
# replace this file (and keep the same method names).
#
# Groq uses the "OpenAI-compatible chat completions" format. Messages are dicts with a role:
#   {"role": "system",    "content": "..."}   instructions for the model
#   {"role": "user",      "content": "..."}   what the human said
#   {"role": "assistant", "content": "...", "tool_calls": [...]}   what the model said or asked for
#   {"role": "tool", "tool_call_id": "...", "content": "..."}      the result of a tool it asked for
# =============================================================================

import json  # note: not used in this file; safe to remove
from groq import AsyncGroq, BadRequestError  # AsyncGroq = async Groq client; BadRequestError = HTTP 400 errors


class GroqService:
    """Chat wrapper around Groq's OpenAI-compatible chat completions API."""

    def __init__(
        self,
        model: str,
        reasoning_effort: str | None = "medium",
        client: AsyncGroq | None = None,
    ):
        # AsyncGroq() reads GROQ_API_KEY from the environment
        # (`client or AsyncGroq()` = use the given client, else create a default one;
        # passing a custom client is handy in tests).
        self.client = client or AsyncGroq()
        self.model = model
        # Only GPT-OSS models accept reasoning_effort ("low" | "medium" | "high"),
        # so for any other model we store None and never send the parameter.
        self.reasoning_effort = (
            reasoning_effort if model.startswith("openai/gpt-oss") else None
        )

    def add_user_message(self, messages: list, content):
        messages.append({"role": "user", "content": content})

    def add_tool_results(self, messages: list, tool_results: list[dict]):
        """Groq/OpenAI format: one `tool` message per tool result."""
        messages.extend(tool_results)  # extend = append every item of the list

    def add_assistant_message(self, messages: list, message):
        """Append a Groq response message, keeping only fields the API accepts back."""
        assistant_message: dict = {
            "role": "assistant",
            "content": message.content or "",  # content can be None when the model only calls tools
        }
        if message.tool_calls:
            # Record which tools the model asked for. The API requires this assistant
            # message to come BEFORE the matching "tool" result messages, and the
            # ids must match (tool_call_id in core/tools.py).
            assistant_message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,  # still a JSON string
                    },
                }
                for call in message.tool_calls
            ]
        messages.append(assistant_message)

    def text_from_message(self, message) -> str:
        return message.content or ""

    @staticmethod
    def _to_groq_tools(tools: list[dict]) -> list[dict]:
        # Translate our provider-neutral tool dicts (name / description / input_schema,
        # built from MCP in core/tools.py) into the shape Groq expects.
        # The MCP "input_schema" is the SAME JSON schema Groq calls "parameters",
        # so this step is just renaming and nesting fields.
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description") or "",
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

    async def chat(
        self,
        messages: list,
        system: str | None = None,
        temperature: float = 0.6,  # randomness: 0 = very predictable, higher = more varied
        tools: list[dict] | None = None,
    ):
        """Returns the assistant message (choices[0].message)."""
        # Put the optional system prompt first, then the whole conversation so far.
        all_messages = (
            [{"role": "system", "content": system}] if system else []
        ) + messages

        params = {
            "model": self.model,
            "messages": all_messages,
            "temperature": temperature,
            "max_completion_tokens": 8000,  # upper limit on the length of the reply
        }
        if self.reasoning_effort:
            params["reasoning_effort"] = self.reasoning_effort
        if tools:
            params["tools"] = self._to_groq_tools(tools)
            # "auto" = the model decides whether to answer directly or call a tool.
            params["tool_choice"] = "auto"

        try:
            # **params unpacks the dict into keyword arguments (model=..., messages=..., ...).
            response = await self.client.chat.completions.create(**params)
        except BadRequestError as e:
            # The model occasionally emits a malformed tool call, which Groq
            # reports as `tool_use_failed`. A single retry usually succeeds.
            if "tool_use_failed" not in str(e):
                raise  # a different 400 error: do not hide it
            response = await self.client.chat.completions.create(**params)

        # `choices` is a list of possible replies; we asked for one, so take the first.
        # choice.message holds the text/tool calls, choice.finish_reason says why it stopped.
        return response.choices[0]
