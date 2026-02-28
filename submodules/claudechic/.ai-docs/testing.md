# Testing

Fast UI tests without SDK dependency, using Textual's testing framework.

## Running Tests

```bash
uv run pytest tests/ -v
```

## Architecture

Tests mock the SDK via `mock_sdk` fixture, enabling fast execution without auth. Three test categories:

- **`test_widgets.py`** - Pure widget tests in isolation
- **`test_app_ui.py`** - Full app UI behavior with mocked SDK
- **`test_app.py`** - Unit tests for app methods

## Key Fixtures

### mock_sdk

Patches `ClaudeSDKClient` so tests don't connect to real SDK:

```python
@pytest.fixture
def mock_sdk():
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.query = AsyncMock()
    # ...
    with patch("claudechic.app.ClaudeSDKClient", return_value=mock_client):
        yield mock_client
```

### wait_for_workers

Waits for async workers to complete:

```python
async def wait_for_workers(app):
    await app.workers.wait_for_complete()
```

### WidgetTestApp

Minimal app for testing widgets in isolation:

```python
class WidgetTestApp(App):
    def __init__(self, widget_factory):
        super().__init__()
        self._widget_factory = widget_factory

    def compose(self):
        yield self._widget_factory()
```

## Writing Tests

### App-level tests

```python
@pytest.mark.asyncio
async def test_example(mock_sdk):
    app = ChatApp()
    async with app.run_test() as pilot:
        input_widget = app.query_one("#input", ChatInput)
        input_widget.text = "/some-command"
        await pilot.press("enter")
        await wait_for_workers(app)

        # Assert on UI state
        assert some_condition
```

### Widget tests

```python
@pytest.mark.asyncio
async def test_widget_behavior():
    app = WidgetTestApp(lambda: MyWidget())
    async with app.run_test() as pilot:
        widget = app.query_one(MyWidget)
        await pilot.press("enter")
        assert widget.some_property == expected
```

### Testing streaming text

Call `append_text` directly on the chat view:

```python
chat_view = app._chat_view
chat_view.append_text("Hello ", new_message=True, parent_tool_id=None)
await pilot.pause()
```

## Key Principles

1. **No SDK auth required** - Tests mock the SDK for speed
2. **Event-driven** - Use `pilot.press()`, `pilot.pause()`, `wait_for_workers()`
3. **No polling loops** - Wait on specific events, not arbitrary delays
4. **Temp files** - Use `tmp_path` fixture for file operations
