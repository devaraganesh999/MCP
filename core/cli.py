# =============================================================================
# core/cli.py : THE TERMINAL UI (input box with autocomplete)
# =============================================================================
# No MCP protocol code lives here. This file only makes typing nicer, using the
# `prompt_toolkit` library:
#   - type "/"  -> a menu of MCP prompts (/format, /summarize) pops up
#   - type "@"  -> a menu of document ids (MCP resources) pops up
# The lists in those menus come from the MCP server (see initialize() below).
#
# prompt_toolkit terms used here:
#   Completer     builds the dropdown menu of suggestions (Tab / auto popup)
#   AutoSuggest   shows faint "ghost text" you can accept (we suggest the argument name)
#   KeyBindings   run our own code when a key is pressed
#   PromptSession the input prompt itself (history, styling, completion)
# =============================================================================

from typing import List, Optional
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
from prompt_toolkit.document import Document
from prompt_toolkit.buffer import Buffer

from core.cli_chat import CliChat


# Shows faint ghost text for the argument after a complete /command.
class CommandAutoSuggest(AutoSuggest):

    def __init__(self, prompts: List):
        self.prompts = prompts  # MCP Prompt objects from the server
        self.prompt_dict = {prompt.name: prompt for prompt in prompts}  # name -> prompt

    def get_suggestion(
        self, buffer: Buffer, document: Document
    ) -> Optional[Suggestion]:
        text = document.text  # everything typed so far

        if not text.startswith("/"):
            return None  # only /commands get suggestions

        parts = text[1:].split()  # "/summarize" -> ["summarize"]

        if len(parts) == 1:
            cmd = parts[0]

            if cmd in self.prompt_dict:
                prompt = self.prompt_dict[cmd]
                # Hint the name of the prompt's first argument (here "doc_id").
                # prompt.arguments comes straight from the MCP server's prompt definition.
                return Suggestion(f" {prompt.arguments[0].name}")

        return None


# One completer for both /commands (MCP prompts) and @mentions (MCP resources).
class UnifiedCompleter(Completer):

    def __init__(self):
        self.prompts = []
        self.prompt_dict = {}
        self.resources = []  # here: the document ids

    def update_prompts(self, prompts: List):
        self.prompts = prompts
        self.prompt_dict = {prompt.name: prompt for prompt in prompts}

    def update_resources(self, resources: List):
        self.resources = resources

    def get_completions(self, document, complete_event):
        # prompt_toolkit calls this while you type; every `yield Completion(...)`
        # becomes one row in the dropdown.
        text = document.text
        text_before_cursor = document.text_before_cursor

        # Case 1: an "@" appears -> suggest document ids that start with what follows it.
        if "@" in text_before_cursor:
            last_at_pos = text_before_cursor.rfind("@")  # position of the last "@"
            prefix = text_before_cursor[last_at_pos + 1 :]  # the letters typed after it

            for resource_id in self.resources:
                if resource_id.lower().startswith(prefix.lower()):
                    yield Completion(
                        resource_id,
                        start_position=-len(prefix),  # replace what was typed after "@"
                        display=resource_id,
                        display_meta="Resource",
                    )
            return

        # Case 2: the line starts with "/" -> it is a command.
        if text.startswith("/"):
            parts = text[1:].split()

            # 2a: still typing the command name ("/su") -> suggest matching prompt names.
            if len(parts) <= 1 and not text.endswith(" "):
                cmd_prefix = parts[0] if parts else ""

                for prompt in self.prompts:
                    if prompt.name.startswith(cmd_prefix):
                        yield Completion(
                            prompt.name,
                            start_position=-len(cmd_prefix),
                            display=f"/{prompt.name}",
                            display_meta=prompt.description or "",  # shows the MCP prompt description
                        )
                return

            # 2b: command typed and a space added ("/summarize ") -> suggest every document id.
            if len(parts) == 1 and text.endswith(" "):
                cmd = parts[0]

                if cmd in self.prompt_dict:
                    for id in self.resources:
                        yield Completion(
                            id,
                            start_position=0,
                            display=id,
                        )
                return

            # 2c: already typing the document id ("/summarize pl") -> filter by prefix.
            if len(parts) >= 2:
                doc_prefix = parts[-1]

                for resource_id in self.resources:
                    if resource_id.lower().startswith(doc_prefix.lower()):
                        yield Completion(
                            resource_id,
                            start_position=-len(doc_prefix),
                            display=resource_id,
                        )
                return


class CliApp:
    def __init__(self, agent: CliChat):
        self.agent = agent  # the CliChat that does the real work
        self.resources = []  # document ids, filled by initialize()
        self.prompts = []  # MCP prompts, filled by initialize()

        self.completer = UnifiedCompleter()

        self.command_autosuggester = CommandAutoSuggest([])

        # Custom key handlers: pressing these keys opens the suggestion menu immediately
        # instead of waiting for Tab.
        self.kb = KeyBindings()

        @self.kb.add("/")
        def _(event):
            buffer = event.app.current_buffer
            # "/" as the very first character -> insert it and open the command menu.
            if buffer.document.is_cursor_at_the_end and not buffer.text:
                buffer.insert_text("/")
                buffer.start_completion(select_first=False)
            else:
                buffer.insert_text("/")

        @self.kb.add("@")
        def _(event):
            buffer = event.app.current_buffer
            buffer.insert_text("@")
            if buffer.document.is_cursor_at_the_end:
                buffer.start_completion(select_first=False)

        @self.kb.add(" ")
        def _(event):
            buffer = event.app.current_buffer
            text = buffer.text

            buffer.insert_text(" ")

            # After "/command " (and for a doc-like argument) open the document menu.
            if text.startswith("/"):
                parts = text[1:].split()

                if len(parts) == 1:
                    buffer.start_completion(select_first=False)
                elif len(parts) == 2:
                    arg = parts[1]
                    if (
                        "doc" in arg.lower()
                        or "file" in arg.lower()
                        or "id" in arg.lower()
                    ):
                        buffer.start_completion(select_first=False)

        self.history = InMemoryHistory()  # Up/Down arrows recall earlier inputs (lost on exit)
        self.session = PromptSession(
            completer=self.completer,
            history=self.history,
            key_bindings=self.kb,
            style=Style.from_dict(
                {
                    "prompt": "#aaaaaa",
                    "completion-menu.completion": "bg:#222222 #ffffff",
                    "completion-menu.completion.current": "bg:#444444 #ffffff",
                }
            ),
            complete_while_typing=True,  # open the menu automatically as you type
            complete_in_thread=True,  # compute suggestions in a background thread so typing never lags
            auto_suggest=self.command_autosuggester,
        )

    async def initialize(self):
        # Ask the MCP server for what the menus should contain.
        await self.refresh_resources()
        await self.refresh_prompts()

    async def refresh_resources(self):
        try:
            # MCP: read the resource docs://documents -> list of document ids.
            self.resources = await self.agent.list_docs_ids()
            self.completer.update_resources(self.resources)
        except Exception as e:
            print(f"Error refreshing resources: {e}")

    async def refresh_prompts(self):
        try:
            # MCP: ListPromptsRequest -> /format and /summarize.
            self.prompts = await self.agent.list_prompts()
            self.completer.update_prompts(self.prompts)
            self.command_autosuggester = CommandAutoSuggest(self.prompts)
            self.session.auto_suggest = self.command_autosuggester
        except Exception as e:
            print(f"Error refreshing prompts: {e}")

    async def run(self):
        # The main loop: read a line, send it to the chat, print the answer, repeat.
        while True:
            try:
                user_input = await self.session.prompt_async("> ")
                if not user_input.strip():
                    continue  # ignore empty lines

                # The whole LLM + MCP tool loop (core/chat.py) happens inside this call.
                response = await self.agent.run(user_input)
                print(f"\nResponse:\n{response}")

            except (KeyboardInterrupt, EOFError):
                # Ctrl+C or Ctrl+D -> leave the loop and exit cleanly.
                break
            except Exception as e:
                # Any other error: show it and keep the chat running.
                print(f"\nError: {e}")
