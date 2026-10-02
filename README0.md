# MCP Chat

A command-line chat app built on **FastMCP 4** (MCP server + client) and the **Groq API**
(default model: `openai/gpt-oss-120b`).

- Chat with the model in your terminal and let it call tools exposed by MCP servers.
- Mention documents with `@doc_id` to inject their contents into your question.
- Run server-defined prompts with `/command doc_id`.
- The bundled MCP server (`mcp_server.py`) can also run **on its own** and be tested with the
  **MCP Inspector** or the `fastmcp` CLI.

```
┌──────────────┐   Groq API (chat + tool calls)   ┌───────────┐
│  CLI (main)  │ ───────────────────────────────▶ │   Groq    │
│  core/*      │ ◀─────────────────────────────── │ gpt-oss   │
└──────┬───────┘                                  └───────────┘
       │ fastmcp.Client (stdio)
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
```

- **`USE_UV`**: `0` (default) starts `mcp_server.py` with the Python that is running the app. This
  works for both uv and pip. Set `1` only if you want the app to launch servers via `uv run`.
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

## 7. Automated test (offline, no API key)

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

## 8. Project layout

```
mcp_chat/
├── main.py              # entry point: starts MCP client(s), model service and CLI
├── mcp_server.py        # FastMCP server: tools, resources, prompts
├── mcp_client.py        # thin wrapper over fastmcp.Client (stdio)
├── core/
│   ├── groq_service.py  # Groq chat completions + tool-call message formats
│   ├── chat.py          # chat loop: model → tool calls → results → model
│   ├── cli_chat.py      # @mentions and /commands on top of Chat
│   ├── cli.py           # prompt_toolkit UI with autocomplete
│   └── tools.py         # lists MCP tools and executes tool calls
├── tests/test_e2e.py    # offline end-to-end test
├── inspector.mcp.json   # server list for the MCP Inspector (stdio + HTTP)
├── pyproject.toml       # dependencies (used by uv)
├── uv.lock              # exact pinned versions (used by uv)
├── requirements.txt     # dependencies (used by pip)
└── .env.example
```

## 9. Extending

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

## 10. Troubleshooting

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
| Windows: `python` not found | Try `py` instead of `python`, or reopen the terminal after installing Python. |

## 11. Notes

- Edits made with `edit_document` are in-memory only (not saved to disk).
- Keep `.env` out of version control (`.gitignore` already excludes it).
- Versions used: fastmcp 4.0.10, mcp 2.x, groq 1.7.x. `uv.lock` pins the exact set for uv; `requirements.txt` sets minimum versions for pip.
