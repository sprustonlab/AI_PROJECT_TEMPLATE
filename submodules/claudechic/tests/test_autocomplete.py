"""Tests for autocomplete widget."""

import pytest
from pathlib import Path

from claudechic import ChatApp
from claudechic.widgets import ChatInput, TextAreaAutoComplete


@pytest.mark.asyncio
async def test_slash_command_autocomplete(mock_sdk, tmp_path: Path):
    """Test slash command autocomplete shows and filters correctly."""
    app = ChatApp()
    async with app.run_test(size=(80, 24)) as pilot:
        input_widget = app.query_one(ChatInput)
        autocomplete = app.query_one(TextAreaAutoComplete)

        # Initially hidden
        assert autocomplete.styles.display == "none"

        # Type / to trigger autocomplete
        input_widget.text = "/"
        await pilot.pause()

        # Should show commands (includes SDK commands, so count varies)
        assert autocomplete.styles.display == "block"
        assert autocomplete.option_list.option_count >= 4  # At least local commands

        # Type more to filter - /worktree should narrow it down
        input_widget.text = "/worktree"
        await pilot.pause()

        # Should show worktree commands (base, finish, cleanup, plus any worktree branches)
        assert autocomplete.option_list.option_count >= 3

        # Type even more to narrow to just one
        # Note: "/worktree f" fuzzy matches "/worktree side-files" too
        input_widget.text = "/worktree fin"
        await pilot.pause()

        # Should show just /worktree finish
        assert autocomplete.option_list.option_count == 1

        # Clear input - should hide
        input_widget.text = ""
        await pilot.pause()

        assert autocomplete.styles.display == "none"


@pytest.mark.asyncio
async def test_path_autocomplete(mock_sdk, tmp_path: Path):
    """Test file path autocomplete with @ trigger."""
    import asyncio

    app = ChatApp()
    async with app.run_test(size=(80, 24)) as pilot:
        autocomplete = app.query_one(TextAreaAutoComplete)
        # Override app's file index to use test files
        assert app.file_index is not None
        app.file_index.files = ["file1.txt", "file2.txt", "subdir/other.py"]

        input_widget = app.query_one(ChatInput)

        # Type @ to start path completion
        input_widget.text = "@"
        # Wait for debounce (150ms) + buffer
        await asyncio.sleep(0.2)
        await pilot.pause()

        # Should show files from index
        assert autocomplete.styles.display == "block"
        assert autocomplete.option_list.option_count == 3

        # Filter to just .txt files
        input_widget.text = "@file"
        # Wait for debounce
        await asyncio.sleep(0.2)
        await pilot.pause()

        assert autocomplete.option_list.option_count == 2


@pytest.mark.asyncio
async def test_tab_completion(mock_sdk):
    """Test that Tab completes the selection."""
    app = ChatApp()
    async with app.run_test(size=(80, 24)) as pilot:
        input_widget = app.query_one(ChatInput)
        autocomplete = app.query_one(TextAreaAutoComplete)

        # Type enough to filter to a unique match
        # Note: "/worktree f" fuzzy matches "/worktree side-files" too
        input_widget.text = "/worktree fin"
        await pilot.pause()

        # Should show just /worktree finish
        assert autocomplete.option_list.option_count == 1

        # Press Tab to complete
        await pilot.press("tab")
        await pilot.pause()

        # Input should now be /worktree finish
        assert input_widget.text == "/worktree finish"
        assert autocomplete.styles.display == "none"


@pytest.mark.asyncio
async def test_suppression_on_history_nav(mock_sdk):
    """Test that autocomplete is suppressed when navigating history."""
    app = ChatApp()
    async with app.run_test(size=(80, 24)) as pilot:
        input_widget = app.query_one(ChatInput)
        autocomplete = app.query_one(TextAreaAutoComplete)

        # Add history entry starting with /
        input_widget._history = ["/agent test"]
        input_widget._history_index = -1

        # Navigate up to history
        await pilot.press("up")
        await pilot.pause()

        # Input should have history content
        assert input_widget.text == "/agent test"
        # Autocomplete should be suppressed (hidden despite matching /)
        assert autocomplete.styles.display == "none"
        assert autocomplete._suppressed is True

        # Type something to clear suppression
        await pilot.press("x")
        await pilot.pause()

        # Suppression should be cleared
        assert autocomplete._suppressed is False
