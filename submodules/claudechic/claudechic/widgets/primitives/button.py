"""Button widget - simple clickable label."""

from textual.message import Message
from textual.widgets import Static


class Button(Static):
    """Simple clickable label with hand cursor and hover state.

    Emits Button.Pressed on click for parent handlers.
    """

    DEFAULT_CSS = """
    Button {
        pointer: pointer;
    }
    """

    class Pressed(Message):
        """Posted when button is clicked."""

        def __init__(self, button: "Button") -> None:
            self.button = button
            super().__init__()

    def on_click(self, event) -> None:
        self.post_message(self.Pressed(self))
