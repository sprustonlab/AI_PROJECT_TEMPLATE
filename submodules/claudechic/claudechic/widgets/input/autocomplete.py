"""Autocomplete widget for TextArea - supports slash commands and file paths."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from operator import itemgetter

from textual import on
from textual.app import ComposeResult
from textual.content import Content
from textual.css.query import NoMatches
from textual.style import Style
from textual.widget import Widget
from textual.widgets import OptionList, TextArea
from textual.widgets.option_list import Option
from textual_autocomplete.fuzzy_search import FuzzySearch

from rich.text import Text

from claudechic.file_index import search_files
from claudechic.shell_complete import (
    complete_command_async,
    complete_path,
    parse_shell_input,
)


@dataclass
class TargetState:
    """State of the target TextArea."""

    text: str
    cursor_position: int  # Linear position in text


class DropdownItem(Option):
    """A single autocomplete option."""

    def __init__(
        self,
        main: str | Content,
        prefix: str | Content | None = None,
        id: str | None = None,
        disabled: bool = False,
    ) -> None:
        self.main = Content(main) if isinstance(main, str) else main
        self.prefix = Content(prefix) if isinstance(prefix, str) else prefix
        prompt = self.main
        if self.prefix:
            prompt = Content.assemble(self.prefix, self.main)
        super().__init__(prompt, id, disabled)

    @property
    def value(self) -> str:
        """Get plain text value of the option (without prefix)."""
        return self.main.plain


class TextAreaAutoComplete(Widget):
    """Autocomplete dropdown for TextArea widgets.

    Supports two modes:
    - Slash commands: triggered by `/` at start of input
    - File paths: triggered by `@` anywhere in input
    """

    DEFAULT_CSS = """\
    TextAreaAutoComplete {
        height: auto;
        width: auto;
        max-height: 16;
        display: none;
        background: $surface;
        border-left: tall $panel;
        overlay: screen;
        padding: 0 1;

        & OptionList {
            width: auto;
            height: auto;
            max-height: 14;
            border: none;
            padding: 0;
            margin: 0;
            scrollbar-size-vertical: 1;
            text-wrap: nowrap;
            color: $text-muted;
            background: transparent;
        }

        & OptionList > .option-list--option-highlighted {
            background: $surface-lighten-1;
            color: $text;
        }

        & .autocomplete--highlight-match {
            text-style: bold;
            color: $primary;
        }
    }
    """

    COMPONENT_CLASSES = {"autocomplete--highlight-match"}

    def __init__(
        self,
        target: TextArea | str,
        slash_commands: list[str] | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._target = target
        self.slash_commands = slash_commands or []
        self._file_index: list[str] = []  # Set by app
        self._fuzzy_search = FuzzySearch()
        self._mode: str | None = None  # "slash" or "path" or None
        self._trigger_pos: int = 0  # Position of / or @
        self._completing: bool = False  # Flag to prevent re-showing during completion
        self._suppressed: bool = False  # Suppress until user types
        self._search_timer = None  # Timer for debounced file search

    @property
    def file_index(self) -> list[str]:
        """Get file index from app if available."""
        if hasattr(self.app, "file_index") and self.app.file_index:  # type: ignore[attr-defined]
            return self.app.file_index.files  # type: ignore[attr-defined]
        return self._file_index

    @file_index.setter
    def file_index(self, value: list[str]) -> None:
        self._file_index = value

    def compose(self) -> ComposeResult:
        option_list = OptionList()
        option_list.can_focus = False
        yield option_list

    @property
    def target(self) -> TextArea:
        """Resolve target widget (accepts selector string or widget instance)."""
        if isinstance(self._target, TextArea):
            return self._target
        return self.screen.query_one(self._target, TextArea)

    @property
    def option_list(self) -> OptionList:
        return self.query_one(OptionList)

    def on_mount(self) -> None:
        self.target.message_signal.subscribe(self, self._on_target_message)
        # Watch selection for cursor moves
        self.watch(self.target, "selection", self._on_selection_change)
        # Register with target for key interception
        if hasattr(self.target, "_autocomplete"):
            self.target._autocomplete = self  # type: ignore[attr-defined]

    def _on_selection_change(self) -> None:
        """Called when cursor position changes."""
        self._handle_text_change()

    def _on_target_message(self, event) -> None:
        """Handle messages from the target TextArea."""
        from textual import events

        if isinstance(event, TextArea.Changed):
            self._handle_text_change()
        elif isinstance(event, events.Key):
            # Clear suppression on any printable key (user is typing)
            if self._suppressed and event.character and event.character.isprintable():
                self._suppressed = False
            self._handle_key(event)

    def _get_cursor_position(self) -> int:
        """Get linear cursor position from TextArea's (row, col) tuple."""
        target = self.target
        row, col = target.cursor_location
        lines = target.text.split("\n")
        pos = sum(len(lines[i]) + 1 for i in range(row)) + col
        return pos

    def _get_target_state(self) -> TargetState:
        return TargetState(
            text=self.target.text,
            cursor_position=self._get_cursor_position(),
        )

    def _handle_text_change(self) -> None:
        """Called when TextArea content changes."""
        if self._completing or self._suppressed:
            return
        state = self._get_target_state()
        # Use text up to cursor, or full text if cursor at start (common when setting text directly)
        text_to_check = (
            state.text[: state.cursor_position]
            if state.cursor_position > 0
            else state.text
        )

        # Detect mode
        self._mode = None
        self._trigger_pos = 0

        # Check for shell command (! prefix or /shell)
        if state.text.startswith("!") or state.text.startswith("/shell "):
            self._mode = "shell"
            self._trigger_pos = 0
        # Check for slash command at start of input
        elif state.text.startswith("/"):
            self._mode = "slash"
            self._trigger_pos = 0
        # Check for @ path reference
        elif "@" in text_to_check:
            at_pos = text_to_check.rfind("@")
            # Make sure it's not in the middle of a word
            if at_pos == 0 or text_to_check[at_pos - 1] in " \n\t":
                self._mode = "path"
                self._trigger_pos = at_pos

        if self._mode == "shell":
            # Shell completion - debounce like path search
            self._cancel_search_timer()
            self._search_timer = self.set_timer(0.1, self._do_shell_search)
        elif self._mode == "path":
            # Debounce file search - cancel pending timer, start new one
            self._cancel_search_timer()
            self._search_timer = self.set_timer(0.15, self._do_path_search)
        elif self._mode == "slash":
            # Slash commands are instant (small list, no file I/O)
            self._cancel_search_timer()
            self._show_options(state)
        else:
            self._cancel_search_timer()
            self.action_hide()

    def _cancel_search_timer(self) -> None:
        """Cancel any pending search timer."""
        if self._search_timer is not None:
            self._search_timer.stop()
            self._search_timer = None

    def _do_path_search(self) -> None:
        """Execute debounced path search."""
        self._search_timer = None
        # Re-check that we're still in path mode with same trigger
        current_state = self._get_target_state()
        text_to_check = (
            current_state.text[: current_state.cursor_position]
            if current_state.cursor_position > 0
            else current_state.text
        )
        if "@" not in text_to_check:
            self.action_hide()
            return
        at_pos = text_to_check.rfind("@")
        if at_pos != self._trigger_pos:
            return  # Trigger position changed, skip this search
        self._show_options(current_state)

    def _do_shell_search(self) -> None:
        """Execute debounced shell completion search (kicks off async)."""
        self._search_timer = None
        current_state = self._get_target_state()
        # Verify still in shell mode
        if not (
            current_state.text.startswith("!")
            or current_state.text.startswith("/shell ")
        ):
            self.action_hide()
            return
        # Run async to avoid blocking on executable scan
        self.run_worker(self._do_shell_search_async(current_state), exclusive=True)

    async def _do_shell_search_async(self, state: TargetState) -> None:
        """Async shell search - runs executable scan off main thread."""
        text = (
            state.text[: state.cursor_position]
            if state.cursor_position > 0
            else state.text
        )
        cmd, arg = parse_shell_input(text)

        cwd = None
        if hasattr(self.app, "_agent") and self.app._agent:  # type: ignore[attr-defined]
            cwd = self.app._agent.cwd  # type: ignore[attr-defined]

        if not cmd:
            completions = await complete_command_async(arg, limit=20)
            candidates = [DropdownItem(c, prefix="$ ") for c in completions]
        else:
            completions = await asyncio.to_thread(complete_path, arg, cwd, 20)
            candidates = [DropdownItem(c, prefix="📄 ") for c in completions]

        # Re-verify we're still in shell mode (user may have changed input)
        current_state = self._get_target_state()
        if not (
            current_state.text.startswith("!")
            or current_state.text.startswith("/shell ")
        ):
            self.action_hide()
            return

        option_list = self.option_list
        option_list.clear_options()
        if candidates:
            option_list.add_options(list(reversed(candidates)))
            option_list.highlighted = len(candidates) - 1

        search = self._get_search_string(current_state)
        if option_list.option_count > 0 and self._should_show(search):
            self.action_show()
            self.call_after_refresh(self._align_to_target)
        else:
            self.action_hide()

    def _show_options(self, state: TargetState) -> None:
        """Build and show options for current state."""
        self._rebuild_options(state)
        if self.option_list.option_count > 0:
            search = self._get_search_string(state)
            if self._should_show(search):
                self.action_show()
                self.call_after_refresh(self._align_to_target)
            else:
                self.action_hide()
        else:
            self.action_hide()

    def _should_show(self, search_string: str) -> bool:
        """Determine if dropdown should be shown."""
        option_count = self.option_list.option_count
        if option_count == 0:
            return False
        # Shell mode requires user to start typing something
        if self._mode == "shell" and not search_string:
            return False
        if option_count == 1:
            first_option = self.option_list.get_option_at_index(0).prompt
            text = (
                first_option.plain
                if isinstance(first_option, Text)
                else str(first_option)
            )
            # For slash commands, compare with the full command
            if self._mode == "slash":
                return text != search_string.lstrip("/")
            return text != search_string
        return True

    def _get_search_string(self, state: TargetState) -> str:
        """Get the string to search/filter with."""
        # Use text up to cursor, or full text if cursor at start
        text_to_check = (
            state.text[: state.cursor_position]
            if state.cursor_position > 0
            else state.text
        )

        if self._mode == "slash":
            return text_to_check  # Include the /
        elif self._mode == "path":
            # Return full query after @ for fuzzy file matching
            return text_to_check[self._trigger_pos + 1 :]
        elif self._mode == "shell":
            # Parse shell input to get what we're completing
            _cmd, arg = parse_shell_input(text_to_check)
            return arg
        return ""

    def _get_candidates(self, state: TargetState) -> list[DropdownItem]:
        """Get autocomplete candidates based on mode."""
        if self._mode == "slash":
            return [DropdownItem(cmd, prefix="⚡ ") for cmd in self.slash_commands]
        elif self._mode == "path":
            return self._get_path_candidates(state)
        # Shell mode is handled async via _do_shell_search_async
        return []

    def _get_path_candidates(self, state: TargetState) -> list[DropdownItem]:
        """Get file path candidates from index with fuzzy matching."""
        query = self._get_search_string(state)
        files = self.file_index

        if not files:
            return []

        # Use fuzzy search with highlighting
        results = search_files(query, files, limit=15)

        items = []
        for path, _score, indices in results:
            # Create highlighted content
            content = Content(path)
            match_style = Style.from_rich_style(
                self.get_component_rich_style(
                    "autocomplete--highlight-match", partial=True
                )
            )
            for idx in indices:
                if idx < len(path):
                    content = content.stylize(match_style, idx, idx + 1)

            items.append(DropdownItem(content, prefix="📄 "))

        return items

    def _rebuild_options(self, state: TargetState) -> None:
        """Rebuild dropdown options."""
        option_list = self.option_list
        option_list.clear_options()

        candidates = self._get_candidates(state)

        # For path/shell mode, candidates are already filtered
        if self._mode in ("path", "shell"):
            matches = candidates
        else:
            search_string = self._get_search_string(state)
            matches = self._get_matches(candidates, search_string)

        if matches:
            # Reverse order so best match is at bottom (near cursor)
            option_list.add_options(list(reversed(matches)))
            option_list.highlighted = len(matches) - 1  # Select bottom item

    def _get_matches(
        self, candidates: list[DropdownItem], search_string: str
    ) -> list[DropdownItem]:
        """Filter and score candidates against search string."""
        if not search_string:
            return candidates

        # For slash commands, strip the leading slashes
        query = search_string.lstrip("/") if self._mode == "slash" else search_string
        if not query:
            return candidates

        matches_and_scores: list[tuple[DropdownItem, float]] = []
        for candidate in candidates:
            candidate_string = candidate.value.strip("/")  # Strip slashes for matching
            score, offsets = self._fuzzy_search.match(query, candidate_string)
            if score > 0:
                # Bonus for match starting at position 0
                if offsets and offsets[0] == 0:
                    score += 10.0
                # Adjust offsets if main has leading / that was stripped for matching
                adjusted_offsets = offsets
                if self._mode == "slash" and candidate.main.plain.startswith("/"):
                    adjusted_offsets = [o + 1 for o in offsets]
                highlighted = self._apply_highlights(
                    candidate.main, tuple(adjusted_offsets)
                )
                item = DropdownItem(
                    main=highlighted,
                    prefix=candidate.prefix,
                    id=candidate.id,
                    disabled=candidate.disabled,
                )
                matches_and_scores.append((item, score))

        matches_and_scores.sort(key=itemgetter(1), reverse=True)
        return [m for m, _ in matches_and_scores]

    def _apply_highlights(
        self, candidate: Content, offsets: tuple[int, ...]
    ) -> Content:
        """Highlight matched characters."""
        match_style = Style.from_rich_style(
            self.get_component_rich_style("autocomplete--highlight-match", partial=True)
        )
        plain = candidate.plain
        for offset in offsets:
            if offset < len(plain) and not plain[offset].isspace():
                candidate = candidate.stylize(match_style, offset, offset + 1)
        return candidate

    def _align_to_target(self) -> None:
        """Position dropdown above input."""
        try:
            from textual.geometry import Offset

            # Get where input is on screen
            input_region = self.target.content_region
            # Get current dropdown height
            _, height = self.option_list.outer_size
            # Position so bottom of dropdown is just above input
            y = input_region.y - height - 1
            x = input_region.x
            self.absolute_offset = Offset(x, max(1, y))
        except Exception:
            pass  # Widget may not be fully mounted

    def handle_key(self, key: str) -> bool:  # type: ignore[override]
        """Handle a key press. Returns True if the key was consumed.

        Call this from the target widget's key handler to intercept keys
        before the target processes them.
        """
        try:
            option_list = self.option_list
        except NoMatches:
            return False

        if not option_list.option_count or not self.display:
            return False

        highlighted = option_list.highlighted or 0

        # Up moves visually up (lower index = top of list)
        # Down moves visually down (higher index = bottom of list)
        if key == "up":
            option_list.highlighted = max(highlighted - 1, 0)
            return True
        elif key == "down":
            option_list.highlighted = min(highlighted + 1, option_list.option_count - 1)
            return True
        elif key == "tab":
            self._complete(highlighted)
            return True
        elif key == "enter":
            self._complete(highlighted, submit=True)
            return True
        elif key == "escape":
            self.action_hide()
            return True

        return False

    def _handle_key(self, event) -> None:
        """Handle key events from target (via message_signal)."""
        from textual import events

        if not isinstance(event, events.Key):
            return

        # Only handle escape via signal (up/down handled by ChatInput actions)
        if event.key == "escape":
            self.handle_key(event.key)

    def _complete(self, option_index: int, submit: bool = False) -> None:
        """Apply the selected completion.

        Args:
            option_index: Index of the option to complete
            submit: If True, also trigger submit after completing (for Enter key)
        """
        if not self.display or self.option_list.option_count == 0:
            return

        option = self.option_list.get_option_at_index(option_index)
        value = (
            option.prompt.plain
            if isinstance(option.prompt, Text)
            else str(option.prompt)
        )
        # Strip prefix (emoji + space or $ + space)
        if value.startswith(("⚡ ", "📄 ", "$ ")):
            value = value[2:]

        state = self._get_target_state()
        self._completing = True
        self._apply_completion(value, state)

        # Use call_after_refresh to hide after all pending updates
        def hide_and_reset():
            self._completing = False
            self.action_hide()
            # Only auto-submit for slash commands (complete actions)
            # File paths are usually part of a larger message
            if (
                submit
                and self._mode == "slash"
                and hasattr(self.target, "action_submit")
            ):
                self.target.action_submit()  # type: ignore[attr-defined]

        self.call_after_refresh(hide_and_reset)

    def _apply_completion(self, value: str, state: TargetState) -> None:
        """Insert the completion into the TextArea."""
        target = self.target
        text = state.text
        # Use actual text length if cursor is at 0
        cursor_pos = state.cursor_position if state.cursor_position > 0 else len(text)

        if self._mode == "slash":
            # Replace entire text when completing a slash command
            # (slash commands are always at the start and standalone)
            target.text = value
            target.move_cursor((0, len(value)))
        elif self._mode == "path":
            # Replace @query with the selected path (keep the @), add trailing space
            replace_start = self._trigger_pos + 1  # After @
            new_text = text[:replace_start] + value + " " + text[cursor_pos:]
            target.text = new_text
            new_cursor = replace_start + len(value) + 1  # +1 for space
            # Convert linear position to (row, col)
            lines = new_text[:new_cursor].split("\n")
            row = len(lines) - 1
            col = len(lines[-1])
            target.move_cursor((row, col))
        elif self._mode == "shell":
            # Replace the current argument being typed
            text_before = text[:cursor_pos]
            cmd, arg = parse_shell_input(text_before)

            if not cmd:
                # Completing command - replace everything after ! or /shell
                if text.startswith("!"):
                    new_text = "!" + value + " "
                else:
                    new_text = "/shell " + value + " "
            else:
                # Completing argument - find where current arg starts
                if arg:
                    # Find the start of the current arg
                    arg_start = text_before.rfind(arg)
                    new_text = text[:arg_start] + value
                else:
                    # No partial arg, just append
                    new_text = text_before + value

            target.text = new_text
            target.move_cursor((0, len(new_text)))

    def action_hide(self) -> None:
        """Hide the autocomplete dropdown."""
        self.styles.display = "none"

    def action_show(self) -> None:
        """Show the autocomplete dropdown."""
        self.styles.display = "block"

    def suppress(self) -> None:
        """Suppress autocomplete until user types a printable character."""
        self._suppressed = True
        self._cancel_search_timer()
        self.action_hide()

    @on(OptionList.OptionSelected)
    def _on_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle mouse click on option."""
        self._complete(event.option_index)
