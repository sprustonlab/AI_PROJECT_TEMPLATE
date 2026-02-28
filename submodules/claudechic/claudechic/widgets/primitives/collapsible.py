"""Custom Collapsible that doesn't auto-scroll on toggle."""

import logging
from collections.abc import Callable, Sequence

from textual.markup import escape as escape_markup
from textual.widget import Widget
from textual.widgets import Collapsible

log = logging.getLogger(__name__)


class QuietCollapsible(Collapsible):
    """Collapsible that doesn't scroll itself into view on toggle.

    The default Textual Collapsible calls scroll_visible() whenever it's
    toggled, which causes scroll jumping in chat interfaces where we want
    to control scrolling ourselves (e.g., tail-following new content).

    Textual 7.4+ sets pointer cursor on Collapsible by default.

    Supports lazy content via content_factory parameter. When provided with
    collapsed=True, content is not composed until first expand (saving ~0.5s
    for sessions with many collapsed tool widgets).
    """

    def __init__(
        self,
        *children: Widget,
        title: str = "Toggle",
        collapsed: bool = True,
        collapsed_symbol: str = "▶",
        expanded_symbol: str = "▼",
        content_factory: Callable[[], Sequence[Widget]] | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        # Store factory before super().__init__ so we can decide whether to pass children
        self._content_factory = content_factory
        self._content_mounted = False
        self._initial_collapsed = collapsed

        # If we have a factory and start collapsed, don't pass children to parent
        # Content will be created lazily on first expand
        if content_factory is not None and collapsed:
            super().__init__(
                title=escape_markup(title),
                collapsed=collapsed,
                collapsed_symbol=collapsed_symbol,
                expanded_symbol=expanded_symbol,
                name=name,
                id=id,
                classes=classes,
                disabled=disabled,
            )
        else:
            # Normal case: pass children through (includes context manager usage)
            super().__init__(
                *children,
                title=escape_markup(title),
                collapsed=collapsed,
                collapsed_symbol=collapsed_symbol,
                expanded_symbol=expanded_symbol,
                name=name,
                id=id,
                classes=classes,
                disabled=disabled,
            )

    def on_mount(self) -> None:
        """Handle initial content mounting for factories when not collapsed."""
        # If factory provided and not collapsed, mount content now (after widget is in DOM)
        if (
            self._content_factory
            and not self._content_mounted
            and not self._initial_collapsed
        ):
            self._mount_lazy_content()

    def _mount_lazy_content(self) -> None:
        """Mount content from factory into Collapsible.Contents."""
        if self._content_mounted or not self._content_factory:
            return
        self._content_mounted = True
        content_widgets = self._content_factory()
        try:
            contents = self.query_one(Collapsible.Contents)
            contents.mount(*content_widgets)
        except Exception:
            log.debug("Failed to mount lazy content", exc_info=True)

    def _watch_collapsed(self, collapsed: bool) -> None:
        """Update collapsed state without auto-scrolling."""
        # Lazy mount: on first expand, call factory and mount content
        if not collapsed and self._content_factory and not self._content_mounted:
            if self.is_mounted:
                self._mount_lazy_content()

        self._update_collapsed(collapsed)
        # Add -expanded class for CSS targeting (Textual only has -collapsed)
        self.set_class(not collapsed, "-expanded")
        # Post the appropriate message
        if collapsed:
            self.post_message(self.Collapsed(self))
        else:
            self.post_message(self.Expanded(self))
        # NOTE: We deliberately omit the scroll_visible() call that
        # the parent class makes here. Scrolling is handled by ChatView.
