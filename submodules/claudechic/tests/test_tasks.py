"""Tests for claudechic.tasks module."""

import asyncio
import pytest

from claudechic.tasks import create_safe_task


class TestCreateSafeTask:
    """Tests for create_safe_task function."""

    @pytest.mark.asyncio
    async def test_successful_task_returns_result(self):
        """Task that succeeds should return its result."""

        async def success():
            return 42

        task = create_safe_task(success(), name="test-success")
        result = await task
        assert result == 42

    @pytest.mark.asyncio
    async def test_exception_is_caught_and_logged(self, caplog):
        """Task that raises exception should be caught and logged."""

        async def failing():
            raise ValueError("test error")

        task = create_safe_task(failing(), name="test-fail")
        result = await task

        # Should return None on failure
        assert result is None
        # Should log the exception
        assert "Task 'test-fail' failed" in caplog.text
        assert "ValueError" in caplog.text

    @pytest.mark.asyncio
    async def test_cancellation_propagates(self):
        """CancelledError should propagate normally, not be caught."""

        async def slow():
            await asyncio.sleep(10)

        task = create_safe_task(slow(), name="test-cancel")
        await asyncio.sleep(0.01)  # Let task start
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_unnamed_task_logs_as_unnamed(self, caplog):
        """Task without name should log as 'unnamed'."""

        async def failing():
            raise ValueError("oops")

        task = create_safe_task(failing())  # No name
        await task

        assert "Task 'unnamed' failed" in caplog.text

    @pytest.mark.asyncio
    async def test_task_returning_none_is_distinguishable_from_failure(self, caplog):
        """Task that legitimately returns None should not log an error."""

        async def returns_none():
            return None

        task = create_safe_task(returns_none(), name="none-returner")
        result = await task

        assert result is None
        assert "none-returner" not in caplog.text  # No error logged

    @pytest.mark.asyncio
    async def test_exception_message_is_logged(self, caplog):
        """Task that raises exception should log the actual error message."""

        async def fails_with_message():
            raise ValueError("specific error message here")

        task = create_safe_task(fails_with_message(), name="message-test")
        await task

        assert "specific error message here" in caplog.text
