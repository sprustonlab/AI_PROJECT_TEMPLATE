"""Tests for vi-mode state machine."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def text_area():
    """Create a mock TextArea with cursor tracking."""
    ta = MagicMock()
    cursor_pos = [(0, 0)]

    def get_cursor():
        return cursor_pos[0]

    def set_cursor(pos):
        cursor_pos[0] = pos

    def word_right():
        row, col = cursor_pos[0]
        cursor_pos[0] = (row, col + 5)

    def word_left():
        row, col = cursor_pos[0]
        cursor_pos[0] = (row, max(0, col - 5))

    type(ta).cursor_location = property(lambda self: get_cursor())
    ta.move_cursor.side_effect = set_cursor
    ta.action_cursor_word_right.side_effect = word_right
    ta.action_cursor_word_left.side_effect = word_left
    ta.action_cursor_line_end.side_effect = lambda: cursor_pos.__setitem__(
        0, (cursor_pos[0][0], 20)
    )
    ta.action_cursor_line_start.side_effect = lambda: cursor_pos.__setitem__(
        0, (cursor_pos[0][0], 0)
    )
    ta.document.end = (10, 0)
    ta.document.get_line.return_value = "hello world"
    ta.text = "hello world\nline two\nline three"
    ta.selected_text = "text"

    # Store cursor_pos for test access
    ta._test_cursor_pos = cursor_pos
    return ta


@pytest.fixture
def handler(text_area):
    """Create a ViHandler with mock TextArea."""
    from claudechic.widgets.input.vi_mode import ViHandler, ViMode

    h = ViHandler(text_area)
    h.state.mode = ViMode.NORMAL
    return h


class TestModeSwitch:
    """Test mode transitions."""

    def test_escape_to_normal(self, handler):
        from claudechic.widgets.input.vi_mode import ViMode

        handler.state.mode = ViMode.INSERT
        handler.handle_key("escape", None)
        assert handler.state.mode == ViMode.NORMAL

    def test_i_to_insert(self, handler):
        from claudechic.widgets.input.vi_mode import ViMode

        handler.handle_key("i", "i")
        assert handler.state.mode == ViMode.INSERT

    def test_a_to_insert(self, handler):
        from claudechic.widgets.input.vi_mode import ViMode

        handler.handle_key("a", "a")
        assert handler.state.mode == ViMode.INSERT

    def test_v_to_visual(self, handler):
        from claudechic.widgets.input.vi_mode import ViMode

        handler.handle_key("v", "v")
        assert handler.state.mode == ViMode.VISUAL

    def test_escape_from_visual(self, handler):
        from claudechic.widgets.input.vi_mode import ViMode

        handler.state.mode = ViMode.VISUAL
        handler.handle_key("escape", None)
        assert handler.state.mode == ViMode.NORMAL

    def test_escape_in_normal_bubbles_up(self, handler):
        """Escape in NORMAL mode should not be consumed (allows agent interrupt)."""
        from claudechic.widgets.input.vi_mode import ViMode

        handler.state.mode = ViMode.NORMAL
        consumed = handler.handle_key("escape", None)
        assert not consumed  # Should bubble up to trigger action_escape


class TestNavigation:
    """Test navigation commands."""

    def test_w_moves_word_right(self, handler, text_area):
        handler.handle_key("w", "w")
        assert text_area.action_cursor_word_right.called

    def test_b_moves_word_left(self, handler, text_area):
        text_area._test_cursor_pos[0] = (0, 10)
        handler.handle_key("b", "b")
        assert text_area.action_cursor_word_left.called

    def test_0_moves_to_line_start(self, handler, text_area):
        text_area._test_cursor_pos[0] = (0, 10)
        handler.handle_key("0", "0")
        assert text_area.action_cursor_line_start.called

    def test_dollar_moves_to_line_end(self, handler, text_area):
        handler.handle_key("$", "$")
        assert text_area.action_cursor_line_end.called

    def test_gg_moves_to_start(self, handler, text_area):
        text_area._test_cursor_pos[0] = (5, 0)
        handler.handle_key("g", "g")
        handler.handle_key("g", "g")
        text_area.move_cursor.assert_called_with((0, 0))

    def test_G_moves_to_end(self, handler, text_area):
        handler.handle_key("G", "G")
        text_area.move_cursor.assert_called_with(text_area.document.end)

    def test_count_prefix(self, handler, text_area):
        handler.handle_key("3", "3")
        handler.handle_key("w", "w")
        assert text_area.action_cursor_word_right.call_count == 3


class TestOperators:
    """Test delete, change, yank operators."""

    def test_dw_deletes_word(self, handler, text_area):
        handler.handle_key("d", "d")
        assert handler.state.pending_operator == "d"
        handler.handle_key("w", "w")
        assert text_area.delete.called
        assert handler.state.pending_operator is None

    def test_cw_changes_word(self, handler, text_area):
        from claudechic.widgets.input.vi_mode import ViMode

        handler.handle_key("c", "c")
        handler.handle_key("w", "w")
        assert text_area.delete.called
        assert handler.state.mode == ViMode.INSERT

    def test_yw_yanks_word(self, handler, text_area):
        handler.handle_key("y", "y")
        handler.handle_key("w", "w")
        assert handler.state.yank_buffer == "text"
        assert not text_area.delete.called

    def test_dd_deletes_line(self, handler, text_area):
        handler.handle_key("d", "d")
        handler.handle_key("d", "d")
        assert text_area.delete.called

    def test_d_dollar_deletes_to_end(self, handler, text_area):
        handler.handle_key("d", "d")
        handler.handle_key("$", "$")
        assert text_area.delete.called

    def test_d3w_deletes_3_words(self, handler, text_area):
        handler.handle_key("d", "d")
        handler.handle_key("3", "3")
        handler.handle_key("w", "w")
        assert text_area.delete.called
        assert text_area.action_cursor_word_right.call_count == 3

    def test_dG_deletes_to_end(self, handler, text_area):
        handler.handle_key("d", "d")
        handler.handle_key("G", "G")
        assert text_area.delete.called

    def test_dgg_deletes_to_start(self, handler, text_area):
        text_area._test_cursor_pos[0] = (5, 0)
        handler.handle_key("d", "d")
        handler.handle_key("g", "g")
        handler.handle_key("g", "g")
        assert text_area.delete.called

    def test_de_deletes_to_word_end(self, handler, text_area):
        handler.handle_key("d", "d")
        handler.handle_key("e", "e")
        assert text_area.delete.called


class TestSimpleEdits:
    """Test x, X, D, C, s, S commands."""

    def test_x_deletes_char(self, handler, text_area):
        handler.handle_key("x", "x")
        assert text_area.action_delete_right.called

    def test_X_deletes_char_before(self, handler, text_area):
        handler.handle_key("X", "X")
        assert text_area.action_delete_left.called

    def test_D_deletes_to_eol(self, handler, text_area):
        handler.handle_key("D", "D")
        assert text_area.action_delete_to_end_of_line.called

    def test_C_changes_to_eol(self, handler, text_area):
        from claudechic.widgets.input.vi_mode import ViMode

        handler.handle_key("C", "C")
        assert text_area.action_delete_to_end_of_line.called
        assert handler.state.mode == ViMode.INSERT


class TestYankPaste:
    """Test yank and paste."""

    def test_p_pastes_after(self, handler, text_area):
        handler.state.yank_buffer = "hello"
        handler.handle_key("p", "p")
        text_area.insert.assert_called_with("hello")

    def test_P_pastes_before(self, handler, text_area):
        handler.state.yank_buffer = "hello"
        handler.handle_key("P", "P")
        text_area.insert.assert_called_with("hello")


class TestUndoRedo:
    """Test undo/redo."""

    def test_u_undoes(self, handler, text_area):
        handler.handle_key("u", "u")
        assert text_area.action_undo.called

    def test_ctrl_r_redoes(self, handler, text_area):
        handler.handle_key("ctrl+r", None)
        assert text_area.action_redo.called
