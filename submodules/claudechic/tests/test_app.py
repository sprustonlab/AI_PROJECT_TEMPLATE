"""Unit tests for ChatApp methods."""

import base64
from pathlib import Path

from claudechic.agent import Agent, ImageAttachment


def test_image_attachment_message_building():
    """Test that images are correctly formatted in messages."""
    agent = Agent(name="test", cwd=Path.cwd())

    # Add a test image
    test_data = base64.b64encode(b"fake image data").decode()
    agent.pending_images.append(
        ImageAttachment("/tmp/test.png", "test.png", "image/png", test_data)
    )

    # Build message
    msg = agent._build_message_with_images("What is this?")

    # Verify structure
    assert msg["type"] == "user"
    content = msg["message"]["content"]
    assert len(content) == 2
    assert content[0] == {"type": "text", "text": "What is this?"}
    assert content[1]["type"] == "image"
    assert content[1]["source"]["type"] == "base64"
    assert content[1]["source"]["media_type"] == "image/png"
    assert content[1]["source"]["data"] == test_data
