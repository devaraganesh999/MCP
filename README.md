# MCP Chat

A command-line chat app built on **FastMCP 4** (MCP server + client) and the **Groq API**
(default model: `openai/gpt-oss-120b`).

- Chat with the model in your terminal and let it call tools exposed by MCP servers.
- Mention documents with `@doc_id` to inject their contents into your question.
- Run server-defined prompts with `/command doc_id`.
- The bundled MCP server (`mcp_server.py`) can also run **on its own** and be tested with the
  **MCP Inspector** or the `fastmcp` CLI.
- The app can reach the server two ways: **stdio** (default, the app starts the server itself) or
  **HTTP** (you start the server separately, like production). See sections 3 and 3b.

```
┌──────────────┐   Groq API (chat + tool calls)   ┌───────────┐
│  CLI (main)  │ ───────────────────────────────▶ │   Groq    │
│  core/*      │ ◀─────────────────────────────── │ gpt-oss   │
└──────┬───────┘                                  └───────────┘
       │ fastmcp.Client (stdio, or HTTP when MCP_SERVER_URL is set)
┌──────▼───────┐
│ mcp_server.py│  tools · resources · prompts
└──────────────┘
```

## How to read the commands in this README

Every command is shown **twice**: once for **uv** and once for **pip**. Use whichever you prefer
(you only need one of them).

| | **uv** | **pip** |
|---|---|---|
| Needs a virtual env you activate? | No, `uv run` handles it | **Yes**, activate it in every new terminal |
| Run a Python file | `uv run main.py` | `python main.py` |
| Run the `fastmcp` CLI | `uv run fastmcp …` | `fastmcp …` |

---

## 1. Prerequisites

| Requirement | Needed for | Check |
|---|---|---|
| Python 3.10+ | everything | `python --version` (on some systems `python3 --version`) |
| [uv](https://docs.astral.sh/uv/) | only if you choose the **uv** path | `uv --version` (install: `pip install uv`) |
| Groq API key | the chat app (not needed to run/test the MCP server) | https://console.groq.com/keys |
| Node.js 22+ (includes `npx`) | **only** the MCP Inspector | `node --version` |

## 2. Setup

### Step 1. Go to the project folder (always run commands from here)

```bash
cd mcp_chat
```

### Step 2. Install dependencies

**With uv**
```bash
uv sync
```
(Creates `.venv` and installs the exact versions from `uv.lock`.)

**With pip**
```bash
python -m venv .venv

# activate it (do this in every new terminal):
source .venv/bin/activate          # macOS / Linux
.venv\Scripts\activate             # Windows (cmd / PowerShell)

pip install -r requirements.txt
```
(`python3` instead of `python` on some systems. You'll see `(.venv)` in your prompt when active.)

### Step 3. Create your `.env`

```bash
cp .env.example .env               # macOS / Linux
copy .env.example .env             # Windows (cmd)
```
Then open `.env` and set your key:

```
GROQ_API_KEY=""                    # required for the chat app
GROQ_MODEL="openai/gpt-oss-120b"   # any Groq model that supports tool use
GROQ_REASONING_EFFORT="medium"     # low | medium | high (GPT-OSS models only)
USE_UV=0                           # see below
MCP_SERVER_URL=""                  # empty = stdio (default). Set for HTTP, see section 3b
MCP_AUTH_TOKEN=""                  # optional bearer token for an HTTP server
```

- **`USE_UV`**: `0` (default) starts `mcp_server.py` with the Python that is running the app. This
  works for both uv and pip. Set `1` only if you want the app to launch servers via `uv run`.
- **`MCP_SERVER_URL`**: leave empty for **stdio**. Set it (for example
  `http://127.0.0.1:8000/mcp`) to connect over **HTTP** to a server you started yourself (section 3b).
- **`MCP_AUTH_TOKEN`**: optional; sent as `Authorization: Bearer <token>` in HTTP mode.
- `llama-3.3-70b-versatile` was deprecated by Groq on 2026-08-16 (Enterprise only), so the default
  is `openai/gpt-oss-120b`. Use `GROQ_REASONING_EFFORT=low` for faster, cheaper replies.

## 3. Run the chat app

**With uv**
```bash
uv run main.py
```

**With pip** (venv activated)
```bash
python main.py
```

`main.py` starts `mcp_server.py` itself as a subprocess (you do **not** start it separately), then
opens the prompt:

```
> What is in @plan.md ?            # @ mentions a document (Tab auto-completes)
> /summarize deposition.md         # / runs an MCP prompt   (Tab auto-completes)
> /format report.pdf               # rewrites the doc in Markdown using the edit tool
> Replace "steps" with "milestones" in plan.md   # the model calls edit_document
```

Exit with `Ctrl+C` or `Ctrl+D`.

**Extra MCP servers:** pass more server scripts as arguments. Their tools are given to the model too.

| uv | pip |
|---|---|
| `uv run main.py my_other_server.py` | `python main.py my_other_server.py` |

### 3b. Run the chat app over HTTP (production-like)

By default the app starts the server itself (stdio), so no second terminal is needed. In production
the server usually runs elsewhere and is reached by **URL**. To reproduce that locally, use **two terminals**.

| | **uv** | **pip** (venv activated) |
|---|---|---|
| **Terminal 1** (server, start it first) | `uv run fastmcp run mcp_server.py --transport http --port 8000` | `fastmcp run mcp_server.py --transport http --port 8000` |
| **Terminal 2** (app) | `uv run main.py` | `python main.py` |

Before starting the app in Terminal 2, set the URL in `.env`:

```
MCP_SERVER_URL="http://127.0.0.1:8000/mcp"
```

(or set it for one run only: `MCP_SERVER_URL=http://127.0.0.1:8000/mcp python main.py` on macOS/Linux,
`$env:MCP_SERVER_URL="http://127.0.0.1:8000/mcp"; python main.py` in PowerShell.)

How to tell it is really using HTTP: each time the app starts, Terminal 1 prints new `POST /mcp` lines.

| | stdio (default) | HTTP |
|---|---|---|
| Who starts the server? | The app | **You**, in another terminal |
| Terminals needed | 1 | 2 |
| Document edits | Reset on every app run | **Persist** while the server runs |
| Switch back | `MCP_SERVER_URL=""` | `MCP_SERVER_URL="http://127.0.0.1:8000/mcp"` |

Notes: start the server **before** the app; the URL must end with `/mcp`; extra server scripts passed to
`main.py` are always started with stdio. `MCP_AUTH_TOKEN` is only needed if your server checks a bearer token.

## 4. Run the MCP server on its own

The server is a normal FastMCP app, so you can run and test it without any LLM or API key.

### 4a. stdio (what the chat app uses)

**With uv**
```bash
uv run fastmcp run mcp_server.py
# or:  uv run mcp_server.py
```

**With pip**
```bash
fastmcp run mcp_server.py
# or:  python mcp_server.py
```

It will look like it hangs. That is normal: a stdio server waits for MCP messages on stdin.
Press `Ctrl+C` to stop. Talk to it through a client (Inspector, `fastmcp` CLI, or the chat app).

### 4b. HTTP (reachable by URL)

**With uv**
```bash
uv run fastmcp run mcp_server.py --transport http --port 8000
```

**With pip**
```bash
fastmcp run mcp_server.py --transport http --port 8000
```

Endpoint: **http://127.0.0.1:8000/mcp**. Opening it in a browser shows an error because it only
speaks MCP, which is expected.

## 5. Test the server with the MCP Inspector

The Inspector is a Node.js tool (run through `npx`), so it needs **Node.js 22+** and internet on the
first run. Everything below works the same on macOS, Linux and Windows.

> **Why you may not see your server:** Inspector 2.x opens on a **Servers** list that only contains
> sample servers (`filesystem-server-default`, `everything-server-default`, `example-server-default`).
> It does **not** know about your project until you launch it with your server as the target, point it
> at a config file, or add it by hand. The methods below do exactly that.
> (`fastmcp dev inspector mcp_server.py` also lands on this sample list, so use the commands below instead.)

You always need **one** extra step in the browser: **open the full URL printed in the terminal**
(it ends in `?MCP_INSPECTOR_API_TOKEN=...`), then switch the server's toggle from *Disconnected* to
*Connected*.

### Method A (recommended): launch the Inspector with your server as the target

Run these from the project folder (`mcp_chat`). Each starts the Inspector with **only your server** in the list.

#### A1. stdio

**With uv**
```bash
npx @modelcontextprotocol/inspector uv run mcp_server.py
```

**With pip** (venv activated, so `python` is the venv's Python)
```bash
npx @modelcontextprotocol/inspector python mcp_server.py
```

Then:
1. Open the printed URL (`http://127.0.0.1:6274?MCP_INSPECTOR_API_TOKEN=...`).
2. On the **Servers** screen you'll see your server (transport **STDIO**). Click its toggle so it shows **Connected**.
3. Use the tabs: **Tools**, **Resources**, **Prompts** (see the checklist below).
4. If it won't connect, open the **Console** tab: it shows the server's error output.

#### A2. HTTP (Streamable HTTP)

**Terminal 1: start the server**

| uv | pip (venv activated) |
|---|---|
| `uv run fastmcp run mcp_server.py --transport http --port 8000` | `fastmcp run mcp_server.py --transport http --port 8000` |

Leave it running. It listens at `http://127.0.0.1:8000/mcp`.

**Terminal 2: start the Inspector pointed at that URL** (same command for uv and pip)
```bash
npx @modelcontextprotocol/inspector --server-url http://127.0.0.1:8000/mcp --transport http
```

Then open the printed URL, find the server (transport **HTTP**), and click its toggle to connect.
Extra tab for HTTP servers: **Network** (raw requests and responses).

> In the server's **Settings**, *Protocol Era* defaults to `legacy`. Your server works with `legacy`,
> `auto` and `modern`, so leave it alone.

### Method B: one config file with all three variants (stdio + HTTP)

The project includes `inspector.mcp.json` with three entries: `mcp-chat-stdio-python`,
`mcp-chat-stdio-uv`, and `mcp-chat-http`.

```bash
npx @modelcontextprotocol/inspector --config inspector.mcp.json
```

Open the printed URL and connect whichever entry you want:
- **`mcp-chat-stdio-uv`**: for uv users.
- **`mcp-chat-stdio-python`**: for pip users (activate the venv first).
- **`mcp-chat-http`**: start the HTTP server first (see A2, Terminal 1).

`--config` is read-only, so it never changes your saved Inspector settings.

### Method C: add the server by hand in the UI

On the **Servers** screen click the blue **Add Servers** button and add a server manually
(labels can differ slightly between Inspector versions; the same menu also offers importing a client config):

| Field | stdio (uv) | stdio (pip) | HTTP |
|---|---|---|---|
| Transport | STDIO | STDIO | HTTP / Streamable HTTP |
| Command | `uv` | `python` (or the full path to `.venv/bin/python`, on Windows `.venv\Scripts\python.exe`) | n/a |
| Arguments | `run mcp_server.py` | `mcp_server.py` | n/a |
| URL | n/a | n/a | `http://127.0.0.1:8000/mcp` |
| Working directory (if asked) | the `mcp_chat` folder | the `mcp_chat` folder | n/a |

Save it, then click the toggle to connect. For HTTP, start the server first (A2, Terminal 1).
Servers you add this way are saved in `~/.mcp-inspector/mcp.json`.

### What to verify in the Inspector

| Tab | Try this | Expected |
|---|---|---|
| **Tools** | `read_doc_contents` → `doc_id = plan.md` | `The plan outlines the steps for the project's implementation.` |
| **Tools** | `read_doc_contents` → `doc_id = nope` | error: `Doc with id nope not found` |
| **Tools** | `edit_document` → `doc_id=plan.md`, `old_str=steps`, `new_str=STEPS` | `Document plan.md updated successfully` |
| **Resources** | `docs://documents` | JSON list of 6 document ids |
| **Resources** (templates) | `docs://documents/{doc_id}` → `spec.txt` | the spec text |
| **Prompts** | `summarize` → `doc_id = report.pdf` | a user message asking for a summary |
| **Prompts** | `format` → `doc_id = report.pdf` | a user message asking to reformat as Markdown |
| **Protocol** | any call | the raw JSON-RPC request and response |

> Edits live in memory only. They reset whenever the server restarts.

### Quick check without a browser (Inspector CLI mode)

Handy to confirm everything works before opening the UI (swap `python` for `uv run` if you use uv):

```bash
npx @modelcontextprotocol/inspector --cli python mcp_server.py --method tools/list
npx @modelcontextprotocol/inspector --cli python mcp_server.py --method tools/call --tool-name read_doc_contents --tool-arg doc_id=plan.md
npx @modelcontextprotocol/inspector --cli python mcp_server.py --method resources/read --uri docs://documents
npx @modelcontextprotocol/inspector --cli python mcp_server.py --method prompts/get --prompt-name summarize --prompt-args doc_id=report.pdf

# HTTP server (start it first, see A2)
npx @modelcontextprotocol/inspector --cli --server-url http://127.0.0.1:8000/mcp --transport http --method tools/list
```

## 6. Test from the terminal (no Inspector needed)

The `fastmcp` CLI talks to the server directly. For **pip**, drop the `uv run` prefix (venv activated).

| What | uv | pip |
|---|---|---|
| List tools, resources, prompts | `uv run fastmcp list mcp_server.py --resources --prompts` | `fastmcp list mcp_server.py --resources --prompts` |
| Call a tool | `uv run fastmcp call mcp_server.py read_doc_contents doc_id=plan.md` | `fastmcp call mcp_server.py read_doc_contents doc_id=plan.md` |
| Read a resource | `uv run fastmcp call mcp_server.py docs://documents` | `fastmcp call mcp_server.py docs://documents` |
| Read a resource template | `uv run fastmcp call mcp_server.py docs://documents/spec.txt` | `fastmcp call mcp_server.py docs://documents/spec.txt` |
| Render a prompt | `uv run fastmcp call mcp_server.py summarize --prompt doc_id=report.pdf` | `fastmcp call mcp_server.py summarize --prompt doc_id=report.pdf` |
| Server summary | `uv run fastmcp inspect mcp_server.py` | `fastmcp inspect mcp_server.py` |
| Against the HTTP server | `uv run fastmcp list http://127.0.0.1:8000/mcp` | `fastmcp list http://127.0.0.1:8000/mcp` |

A target containing `://` is treated as a resource URI; `--prompt` treats the target as a prompt name.

## 7. Test the MCP client

Sections 5 and 6 test the **server** (the Inspector and the `fastmcp` CLI are *other people's clients*).
This section tests **our own client**, `mcp_client.py`: the class the app uses to start a server,
list tools, call tools, read resources and fetch prompts. No Groq key and no internet are needed
for levels 1 and 2.

There are three levels. Run them from the project folder (`mcp_chat`).

| Level | What it proves | Needs Groq key? |
|---|---|---|
| **1. Smoke test** | The client can start the server and talk to it | No |
| **2. Full client test** | Every client method works, including the error paths | No |
| **3. End to end** | Client + LLM + tools together, in the real app | **Yes** |

### Level 1: smoke test (about 2 seconds)

`mcp_client.py` has a small test built in. It starts `mcp_server.py` as a child process, lists the
tools and reads the document list.

**With uv**
```bash
uv run mcp_client.py
```

**With pip** (venv activated)
```bash
python mcp_client.py
```

Expected output:
```
transport: stdio (starts its own server)
tools: ['read_doc_contents', 'edit_document']
docs: ['deposition.md', 'report.pdf', 'financials.docx', 'outlook.pdf', 'plan.md', 'spec.txt']
```

If you see the `tools:` and `docs:` lines, the client started the server, completed the MCP handshake and
exchanged `ListToolsRequest` and `ReadResourceRequest` messages successfully.

**Same smoke test over HTTP.** Start the server in another terminal (section 4b), then set `MCP_SERVER_URL`:

| Shell | Command (uv: prefix with `uv run`; pip: as shown) |
|---|---|
| macOS / Linux | `MCP_SERVER_URL=http://127.0.0.1:8000/mcp python mcp_client.py` |
| Windows PowerShell | `$env:MCP_SERVER_URL="http://127.0.0.1:8000/mcp"; python mcp_client.py` |
| Windows cmd | `set MCP_SERVER_URL=http://127.0.0.1:8000/mcp` then `python mcp_client.py` |

The first output line then reads `transport: HTTP http://127.0.0.1:8000/mcp`.

### Level 2: full client test

`tests/test_client.py` calls **every** client method and also checks the failure cases (unknown
document, text not found when editing).

**With uv**
```bash
uv run python tests/test_client.py
```

**With pip** (venv activated)
```bash
python tests/test_client.py
```

What it checks:

| Client method | MCP message | Checks |
|---|---|---|
| `list_tools()` | `ListToolsRequest` | the two tools exist and `doc_id` is required |
| `call_tool()` | `CallToolRequest` | a good read, an unknown doc (`is_error` is `True`, no Python exception), an edit, reading the edit back, an edit whose text is missing |
| `read_resource()` | `ReadResourceRequest` | `docs://documents` becomes a Python list of 6 ids; `docs://documents/spec.txt` returns text |
| `list_prompts()` | `ListPromptsRequest` | `format` and `summarize` exist |
| `get_prompt()` | `GetPromptRequest` | the returned user message contains the doc id you passed |

Expected last line: `ALL CLIENT TESTS PASSED` (exit code `0`; on failure it prints the failed
checks and exits with `1`). In stdio mode every run starts a fresh server.

**Over HTTP**, start the server first (section 4b), then set `MCP_SERVER_URL` exactly as in level 1:

| Shell | Command |
|---|---|
| macOS / Linux | `MCP_SERVER_URL=http://127.0.0.1:8000/mcp python tests/test_client.py` (uv: `uv run python ...`) |
| Windows PowerShell | `$env:MCP_SERVER_URL="http://127.0.0.1:8000/mcp"; python tests/test_client.py` |

An HTTP server keeps running between tests, so the test **undoes its own edit**; you can rerun it as often
as you like. The first line printed shows which transport was used.

You may also see a few `Error calling tool ...` log lines in the terminal. They are expected: two checks
deliberately trigger a tool error (unknown document, text not found) to prove the client reports it correctly.

### Level 3: end to end with the real app

Needs your Groq key in `.env` (section 2, step 3).

| uv | pip (venv activated) |
|---|---|
| `uv run main.py` | `python main.py` |

Then try, in this order:

| You type | What it exercises in the client |
|---|---|
| `/summarize plan.md` | `list_prompts` (menu) + `get_prompt`, then the model calls `read_doc_contents` via `call_tool` |
| `What is in @plan.md ?` | `read_resource` for `docs://documents` (menu) and `docs://documents/plan.md` |
| `Replace "steps" with "milestones" in plan.md` | `call_tool` with `edit_document` |
| `Read the document nope.md` | a failed tool: the error comes back as `is_error` and the model explains it |

To test several servers at once, pass another server script: `uv run main.py other_server.py` or
`python main.py other_server.py`. Each script gets its own client and its tools are offered to the model.

### Good to know

- `MCPClient` speaks **stdio** (it launches the server itself) **and HTTP** (it connects to a running
  server) depending on whether you pass `command`/`args` or a `url`. The Inspector and `fastmcp` CLI
  (sections 5 and 6) are still handy for testing the server itself.
- The client starts the server with `sys.executable`, the Python that is running your script, so it
  uses the same virtual environment for both uv and pip. (More in the comments of `main.py`.)
- The level 1 smoke test uses the relative path `mcp_server.py`, so run it from the project folder.
  The level 2 test uses an absolute path and works from anywhere.

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: fastmcp` (pip) | Activate the venv and run `pip install -r requirements.txt`. |
| Server file not found (level 1) | Run from the project folder (`cd mcp_chat`). |
| `Client failed to connect: All connection attempts failed` (HTTP) | The server isn't running or the URL is wrong. Start it first (section 4b) and make sure the URL ends with `/mcp`. |
| The test hangs for a long time | The server probably failed to start. Run `python mcp_server.py` on its own and read the error. |
| Connection closed right away | Something printed to **stdout** in the server, or the server crashed on import. Fix the server error first. |

## 8. Automated test (offline, no API key)

**With uv**
```bash
uv run python tests/test_e2e.py
```

**With pip** (venv activated)
```bash
python tests/test_e2e.py
```

It runs the real MCP server over stdio and the real Groq SDK against a mocked HTTP transport. It
checks the tool-call loop, request format (`model`, `reasoning_effort`, `tools`), `@doc` resources,
`/prompts`, and tool error handling. Expected last line: `ALL TESTS PASSED`.

It does **not** call Groq itself. To verify your key and model end to end, run the app (section 3)
and ask something like `Summarize @plan.md`.

## 9. Project layout

```
mcp_chat/
├── main.py              # entry point: starts MCP client(s), model service and CLI
├── mcp_server.py        # FastMCP server: tools, resources, prompts
├── mcp_client.py        # thin wrapper over fastmcp.Client (stdio or HTTP)
├── core/
│   ├── groq_service.py  # Groq chat completions + tool-call message formats
│   ├── chat.py          # chat loop: model → tool calls → results → model
│   ├── cli_chat.py      # @mentions and /commands on top of Chat
│   ├── cli.py           # prompt_toolkit UI with autocomplete
│   └── tools.py         # lists MCP tools and executes tool calls
├── tests/test_e2e.py    # offline end-to-end test
├── tests/test_client.py # test of mcp_client.py, stdio or HTTP (section 7)
├── inspector.mcp.json   # server list for the MCP Inspector (stdio + HTTP)
├── pyproject.toml       # dependencies (used by uv)
├── uv.lock              # exact pinned versions (used by uv)
├── requirements.txt     # dependencies (used by pip)
└── .env.example
```

**Reading the code.** Every file has beginner-friendly comments. A good reading order:
`mcp_server.py` → `mcp_client.py` → `main.py` → `core/chat.py` → `core/tools.py` → the rest.
(`inspector.mcp.json` cannot hold comments because JSON has none; section 5, Method B explains it.)

Python terms you will meet in the code:

| Term | Meaning |
|---|---|
| `sys.executable` | Full path of the Python running the script. Used to start the server with the **same** Python and packages as the app (works for uv and pip). |
| `sys.platform` | OS name: `"win32"` = Windows (also 64-bit), `"linux"`, `"darwin"` = macOS. |
| `sys.argv` | The command-line words. `python main.py other.py` gives `sys.argv[1:] == ["other.py"]`. |
| `WindowsProactorEventLoopPolicy` | Windows needs asyncio's Proactor event loop to start subprocesses. Python 3.8+ already defaults to it, so the `win32` check is a safety net. |
| `if __name__ == "__main__":` | Runs only when the file is executed directly, not when it is imported. |
| `async with` / `AsyncExitStack` | Open a connection and always close it afterwards, even on errors. The stack handles many at once. |

## 10. Extending

All in `mcp_server.py`:

```python
docs["notes.md"] = "My new document"          # new document

@mcp.tool                                      # new tool
def word_count(doc_id: str) -> int:
    return len(docs[doc_id].split())

@mcp.prompt                                    # new /command (takes a doc_id)
def translate(doc_id: str) -> str:
    return f"Translate document {doc_id} to French using the read_doc_contents tool."
```

Restart the chat app (in the Inspector, disconnect and reconnect the server). New tools are picked up
automatically. New prompts appear as `/translate`. The CLI expects prompts to take a single
`doc_id` argument.

**Adding a dependency**

| uv | pip |
|---|---|
| `uv add <package>` | `pip install <package>` then add it to `requirements.txt` |

## 11. Troubleshooting

| Symptom | Fix |
|---|---|
| `AssertionError: GROQ_API_KEY cannot be empty` | Create `.env` (copy `.env.example`) and set the key. Run from the project folder. |
| `401` / `invalid_api_key` | Key is wrong or has stray quotes/spaces. |
| `model_decommissioned` / `model_not_found` | Set `GROQ_MODEL` to a current tool-capable model, e.g. `openai/gpt-oss-120b`. |
| `429` rate limit | Wait and retry, lower `GROQ_REASONING_EFFORT`, or upgrade your Groq plan. |
| `tool_use_failed` (400) | The model produced a malformed tool call. The app retries once; if it persists, rephrase or retry. |
| `ModuleNotFoundError: core` / `mcp_client` | Run commands from the project root (`cd mcp_chat`). |
| `ModuleNotFoundError: fastmcp` / `groq` (pip) | The venv isn't activated, or you skipped `pip install -r requirements.txt`. |
| `fastmcp: command not found` (pip) | Activate the venv (`source .venv/bin/activate`) or run `python -m fastmcp …`. |
| `ModuleNotFoundError: mcp.server.fastmcp` | Old code or an old pin. This project uses `from fastmcp import FastMCP` (mcp SDK v2 removed that path). Don't add `mcp[cli]<2`. |
| `uv: command not found` | `pip install uv`, or use the pip commands instead. |
| `npx: command not found` / Inspector won't start | Install Node.js 22+ (https://nodejs.org). |
| Inspector shows only `filesystem-server-default`, `everything-server-default`, `example-server-default` | Those are samples. Launch with your server as the target (section 5, Method A/B) or add it with **Add Servers** (Method C). |
| Inspector UI says unauthorized | Open the full URL printed in the terminal (it includes `MCP_INSPECTOR_API_TOKEN`). |
| Inspector stdio server stays *Disconnected* / errors | Open the **Console** tab for the server's stderr. Usually the wrong `python` (pip: activate the venv) or running outside the `mcp_chat` folder. |
| Inspector HTTP server won't connect | Make sure the server is running (A2, Terminal 1) and the URL ends with `/mcp`. |
| `No servers found in config file` (Inspector CLI) | Don't pass `--no-healthcheck` outside Docker; put `--cli` first, then your command. |
| Port 6274/6275/8000 already in use | Inspector: set `CLIENT_PORT=6280` (macOS/Linux: `CLIENT_PORT=6280 npx @modelcontextprotocol/inspector …`). Server: `fastmcp run … --port 8001` and use that port in the URL. |
| Server "hangs" when run directly | Expected for stdio. See 4a. |
| App still starts its own server although I want HTTP | `MCP_SERVER_URL` is empty or `.env` wasn't loaded. Run from the project folder and check the value. |
| `Client failed to connect` after setting `MCP_SERVER_URL` | Start the HTTP server first (section 4b); the URL must end with `/mcp`; check the port. |
| HTTP: edits are still there after restarting the app | Expected: the HTTP server keeps its in-memory documents until **it** restarts. |
| Windows: `python` not found | Try `py` instead of `python`, or reopen the terminal after installing Python. |

## 12. Notes

- Edits made with `edit_document` are in-memory only (not saved to disk).
- Keep `.env` out of version control (`.gitignore` already excludes it).
- Versions used: fastmcp 4.0.10, mcp 2.x, groq 1.7.x. `uv.lock` pins the exact set for uv; `requirements.txt` sets minimum versions for pip.
