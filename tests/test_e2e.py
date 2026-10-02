"""Offline end-to-end test.

Real: FastMCP server (stdio subprocess), FastMCP client, tool loop, Groq SDK
request building / response parsing.  Mocked: the HTTP transport to Groq.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from groq import AsyncGroq

from mcp_client import MCPClient
from core.cli_chat import CliChat
from core.groq_service import GroqService

requests: list[dict] = []


def completion(message: dict, finish_reason: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 0,
            "model": "openai/gpt-oss-120b",
            "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )


def handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    requests.append(body)
    last = body["messages"][-1]
    # gpt-oss style: includes a `reasoning` field and null content on tool calls
    if last["role"] == "tool":
        return completion(
            {"role": "assistant", "reasoning": "summarize tool output",
             "content": f"The doc says: {last['content']}"},
            "stop",
        )
    return completion(
        {
            "role": "assistant",
            "content": None,
            "reasoning": "I should read the doc",
            "tool_calls": [{
                "id": "fc_1", "type": "function",
                "function": {"name": "read_doc_contents",
                             "arguments": json.dumps({"doc_id": "plan.md"})},
            }],
        },
        "tool_calls",
    )


async def main():
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    groq = AsyncGroq(api_key="test", http_client=http)
    llm = GroqService(model="openai/gpt-oss-120b", reasoning_effort="low", client=groq)

    async with MCPClient(sys.executable, [os.path.join(os.path.dirname(__file__), "..", "mcp_server.py")]) as dc:
        chat = CliChat(dc, {"doc": dc}, llm)

        # resources + prompts
        assert "plan.md" in await chat.list_docs_ids()
        assert {p.name for p in await chat.list_prompts()} == {"format", "summarize"}

        # full tool-call loop through the real Groq SDK
        answer = await chat.run("What does plan.md say?")
        assert answer == "The doc says: The plan outlines the steps for the project's implementation.", answer

        first, second = requests
        assert first["model"] == "openai/gpt-oss-120b"
        assert first["reasoning_effort"] == "low"
        assert first["tool_choice"] == "auto"
        names = {t["function"]["name"] for t in first["tools"]}
        assert names == {"read_doc_contents", "edit_document"}, names
        # assistant tool_call message echoed back without the `reasoning` field
        asst = second["messages"][-2]
        assert asst["role"] == "assistant" and "reasoning" not in asst
        assert asst["tool_calls"][0]["function"]["name"] == "read_doc_contents"
        assert second["messages"][-1] == {
            "role": "tool", "tool_call_id": "fc_1",
            "content": "The plan outlines the steps for the project's implementation.",
        }

        # slash command -> prompt messages
        chat.messages.clear()
        await chat._process_query("/summarize report.pdf")
        assert chat.messages[0]["role"] == "user" and "report.pdf" in chat.messages[0]["content"]

        # tool errors surface as is_error
        r = await dc.call_tool("read_doc_contents", {"doc_id": "nope"})
        assert r.is_error and "not found" in r.content[0].text

        # edit tool
        r = await dc.call_tool("edit_document", {"doc_id": "plan.md", "old_str": "steps", "new_str": "STEPS"})
        assert not r.is_error
        assert "STEPS" in await chat.get_doc_content("plan.md")

    # reasoning_effort is dropped for non-gpt-oss models
    assert GroqService("llama-3.3-70b-versatile", client=groq).reasoning_effort is None
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
