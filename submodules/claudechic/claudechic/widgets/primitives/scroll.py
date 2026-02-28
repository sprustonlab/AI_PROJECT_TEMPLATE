"""Auto-hiding scrollbar container."""

from textual.containers import VerticalScroll
from textual.scrollbar import ScrollTo


class AutoHideScroll(VerticalScroll):
    """VerticalScroll with always-visible scrollbar and smart tailing.

    Tracks whether user is at bottom to enable/disable auto-scroll on new content.

    Tailing mode tracks user intent: disabled when user scrolls up, re-enabled
    only when user explicitly scrolls to bottom.
    """

    can_focus = False

    DEFAULT_CSS = """
    AutoHideScroll {
        scrollbar-size-vertical: 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._tailing = True

    def _is_near_bottom(self) -> bool:
        """Check if scroll position is near the bottom."""
        return self.scroll_y >= self.max_scroll_y - 50

    def _user_scrolled_up(self) -> None:
        """User initiated upward scroll - disable tailing."""
        self._tailing = False

    def _user_scrolled_down(self) -> None:
        """User initiated downward scroll - re-enable tailing if at bottom."""
        if self._is_near_bottom():
            self._tailing = True

    def action_scroll_up(self) -> None:
        """User scrolled up via keyboard."""
        self._user_scrolled_up()
        super().action_scroll_up()

    def action_scroll_down(self) -> None:
        """User scrolled down via keyboard."""
        super().action_scroll_down()
        # Check after scroll completes
        self.call_after_refresh(self._user_scrolled_down)

    def action_page_up(self) -> None:
        """User paged up via keyboard."""
        self._user_scrolled_up()
        super().action_page_up()

    def action_page_down(self) -> None:
        """User paged down via keyboard."""
        super().action_page_down()
        self.call_after_refresh(self._user_scrolled_down)

    def _on_mouse_scroll_up(self, event) -> None:
        """User scrolled up via mouse wheel."""
        self._user_scrolled_up()
        super()._on_mouse_scroll_up(event)

    def _on_mouse_scroll_down(self, event) -> None:
        """User scrolled down via mouse wheel."""
        super()._on_mouse_scroll_down(event)
        self.call_after_refresh(self._user_scrolled_down)

    def _on_scroll_to(self, message: ScrollTo) -> None:
        """User dragged scrollbar."""
        if message.y is not None:
            if message.y < self.scroll_y:
                self._user_scrolled_up()
            else:
                # Dragging down - check after scroll
                self.call_after_refresh(self._user_scrolled_down)
        super()._on_scroll_to(message)

    def scroll_if_tailing(self) -> None:
        """Scroll to end if in tailing mode."""
        if self._tailing:
            self.scroll_end(animate=False)
