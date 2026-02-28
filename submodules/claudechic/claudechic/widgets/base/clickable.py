"""Clickable label widget - static text with pointer cursor."""

from textual.widgets import Static


class ClickableLabel(Static):
    """A static label that is clickable with pointer cursor.

    Base class for labels that respond to clicks. Override on_click()
    to handle clicks, or post custom messages.

    Example:
        class MyLabel(ClickableLabel):
            class Clicked(Message):
                pass

            def on_click(self, event) -> None:
                self.post_message(self.Clicked())
    """

    DEFAULT_CSS = """
    ClickableLabel {
        pointer: pointer;
    }
    """
