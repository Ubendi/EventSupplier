"""
Unit tests for vlc_main.py module.

Tests the extracted helper functions:
- execute_action: VLC action execution and MQTT publishing
- should_retry: Retry logic decision
- process_ok_status: OK status handling
- process_error_status: Error status handling
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

# Import the functions we refactored for testing
from vlc_interface.vlc_main import (
    execute_action,
    should_retry,
    process_ok_status,
    process_error_status,
)


# ============================================================================
# execute_action Tests
# ============================================================================

class TestExecuteAction:
    """Tests for the execute_action function."""

    @pytest.mark.asyncio
    async def test_execute_action_success(self, mock_mqtt_interface, mock_emitter, caplog):
        """Test successful action execution and MQTT publishing."""
        # Setup mocks
        test_topic = "vlc_update"
        test_action = "test_action_object"
        test_message = "test_message_content"
        
        mock_emitter.send.return_value = MagicMock(message=test_message)
        mock_mqtt_interface.publish_event = AsyncMock(
            return_value=MagicMock(status="success")
        )

        # Execute
        result = await execute_action(
            topic=test_topic,
            action=test_action,
            emitter=mock_emitter,
            mqtt_interface=mock_mqtt_interface
        )

        # Assertions
        mock_emitter.send.assert_called_once_with(test_action)
        mock_mqtt_interface.publish_event.assert_called_once_with(test_topic, test_message)
        assert result.status == "success"
        assert f"Message sent to {test_topic}" in caplog.text

    @pytest.mark.asyncio
    async def test_execute_action_mqtt_failure(self, mock_mqtt_interface, mock_emitter, caplog):
        """Test handling of MQTT publish failure."""
        test_topic = "vlc_errors"
        test_action = "error_action"
        
        mock_emitter.send.return_value = MagicMock(message="error_msg")
        mock_mqtt_interface.publish_event = AsyncMock(
            return_value=MagicMock(status="error", error="Connection timeout")
        )

        # Execute
        result = await execute_action(
            topic=test_topic,
            action=test_action,
            emitter=mock_emitter,
            mqtt_interface=mock_mqtt_interface
        )

        # Assertions
        mock_emitter.send.assert_called_once()
        mock_mqtt_interface.publish_event.assert_called_once()
        assert result.status == "error"
        # Should still log the message even on failure
        assert f"Message sent to {test_topic}" in caplog.text

    @pytest.mark.asyncio
    async def test_execute_action_vlc_error(self, mock_mqtt_interface, mock_emitter, caplog):
        """Test handling of VLC emitter error."""
        test_topic = "vlc_update"
        test_action = "bad_action"
        
        # Simulate VLC emitter raising an exception
        mock_emitter.send.side_effect = RuntimeError("VLC command failed")
        mock_mqtt_interface.publish_event = AsyncMock()

        # Execute and expect exception
        with pytest.raises(RuntimeError, match="VLC command failed"):
            await execute_action(
                topic=test_topic,
                action=test_action,
                emitter=mock_emitter,
                mqtt_interface=mock_mqtt_interface
            )


# ============================================================================
# should_retry Tests
# ============================================================================

class TestShouldRetry:
    """Tests for the should_retry pure function."""

    def test_should_retry_within_limit(self):
        """Test retry is allowed when under max retries."""
        assert should_retry(is_retrying=True, retry_count=1, max_retries=3) is True
        assert should_retry(is_retrying=True, retry_count=2, max_retries=3) is True
        assert should_retry(is_retrying=True, retry_count=3, max_retries=3) is True

    def test_should_retry_exceeded_limit(self):
        """Test retry is denied when max retries exceeded."""
        assert should_retry(is_retrying=True, retry_count=4, max_retries=3) is False
        assert should_retry(is_retrying=True, retry_count=10, max_retries=3) is False

    def test_should_retry_not_in_retry_mode(self):
        """Test retry is denied when not in retrying state."""
        assert should_retry(is_retrying=False, retry_count=1, max_retries=3) is False
        assert should_retry(is_retrying=False, retry_count=0, max_retries=3) is False

    def test_should_retry_edge_cases(self):
        """Test edge cases for retry logic."""
        # When max_retries is 0, any retry_count >= 1 should fail
        assert should_retry(is_retrying=True, retry_count=1, max_retries=0) is False
        assert should_retry(is_retrying=True, retry_count=0, max_retries=0) is True  # 0 <= 0, but count starts at 1 in practice
        # When retry_count equals max_retries, should still retry
        assert should_retry(is_retrying=True, retry_count=3, max_retries=3) is True


# ============================================================================
# process_ok_status Tests
# ============================================================================

class TestProcessOkStatus:
    """Tests for the process_ok_status function."""

    def test_new_media_triggers_all_actions(self, mock_builder, mock_status_ok):
        """Test that new media triggers position, subtitle, and audio actions."""
        # Execute with no previous media
        new_media, actions = process_ok_status(
            status=mock_status_ok,
            last_media=None,
            builder=mock_builder,
            emitter=MagicMock(),
            mqtt_interface=MagicMock()
        )

        # Assertions
        assert new_media == "test_movie.mp4"
        assert len(actions) == 3  # position, subtitle, audio
        
        # Check action types
        topics = [action[0] for action in actions]
        assert topics.count("vlc_update") == 3
        
        # Check builder calls
        mock_builder.set_position_action.assert_called_once_with("test_movie.mp4")
        mock_builder.select_subtitle_stream_action.assert_called_once_with("English")
        mock_builder.select_audio_stream_action.assert_called_once()

    def test_same_media_triggers_position_update(self, mock_builder, mock_status_ok):
        """Test that same media only triggers position update."""
        # Execute with same media as before
        new_media, actions = process_ok_status(
            status=mock_status_ok,
            last_media="test_movie.mp4",
            builder=mock_builder,
            emitter=MagicMock(),
            mqtt_interface=MagicMock()
        )

        # Assertions
        assert new_media == "test_movie.mp4"  # Same media
        assert len(actions) == 1  # Only position update
        assert actions[0][0] == "vlc_positions"
        
        # Builder should only be called for position update
        mock_builder.upsert_position_action.assert_called_once_with("test_movie.mp4", 10.5)
        mock_builder.set_position_action.assert_not_called()

    def test_different_media_clears_previous_state(self, mock_builder, mock_status_ok):
        """Test that different media is detected and triggers setup."""
        # Execute with different previous media
        new_media, actions = process_ok_status(
            status=mock_status_ok,
            last_media="old_movie.mp4",
            builder=mock_builder,
            emitter=MagicMock(),
            mqtt_interface=MagicMock()
        )

        assert new_media == "test_movie.mp4"
        assert len(actions) == 3  # Full setup for new media


# ============================================================================
# process_error_status Tests
# ============================================================================

class TestProcessErrorStatus:
    """Tests for the process_error_status function."""

    def test_first_error_publishes_error(self, mock_builder, mock_status_error):
        """Test that first error publishes to vlc_errors topic."""
        # No previous media, first error
        new_media, new_error, retry_count, is_retrying, error_action = process_error_status(
            status=mock_status_error,
            last_media=None,
            last_error=None,
            retry_count=1,
            max_retries=3,
            is_retrying=False,
            builder=mock_builder
        )

        # Should publish error since we're not in retry mode
        assert error_action is not None
        assert error_action[0] == "vlc_errors"
        assert new_media is None
        assert new_error == "Connection refused"
        assert retry_count == 1
        assert is_retrying is False

    def test_retry_mode_increment_counter(self, mock_builder, mock_status_error):
        """Test that in retry mode, counter increments."""
        # Had media before (so we're in retry mode)
        new_media, new_error, retry_count, is_retrying, error_action = process_error_status(
            status=mock_status_error,
            last_media="movie.mp4",
            last_error=None,
            retry_count=1,
            max_retries=3,
            is_retrying=False,
            builder=mock_builder
        )

        # First call enters retry mode and increments
        assert new_media == "movie.mp4"
        assert retry_count == 2
        assert is_retrying is True
        assert error_action is None  # In retry mode, no error published

    def test_max_retries_clears_media(self, mock_builder, mock_status_error):
        """Test that max retries reached clears last media."""
        # Already retrying at max
        new_media, new_error, retry_count, is_retrying, error_action = process_error_status(
            status=mock_status_error,
            last_media="movie.mp4",
            last_error="Connection refused",
            retry_count=3,
            max_retries=3,
            is_retrying=True,
            builder=mock_builder
        )

        # Max retries reached - reset
        assert new_media is None
        assert new_error == "Connection refused"
        assert retry_count == 1  # Reset counter
        assert is_retrying is False  # Exit retry mode
        assert error_action is None

    def test_new_error_updates_error_state(self, mock_builder, mock_status_error):
        """Test that new error updates last_error."""
        # Create mock with different error
        mock_status = MagicMock()
        mock_status.status = "error"
        mock_status.payload = {}
        mock_status.error = "New error message"

        new_media, new_error, retry_count, is_retrying, error_action = process_error_status(
            status=mock_status,
            last_media=None,
            last_error="Old error",
            retry_count=1,
            max_retries=3,
            is_retrying=False,
            builder=mock_builder
        )

        assert new_error == "New error message"

    def test_same_error_no_update(self, mock_builder, mock_status_error):
        """Test that same error doesn't update last_error."""
        new_media, new_error, retry_count, is_retrying, error_action = process_error_status(
            status=mock_status_error,
            last_media=None,
            last_error="Connection refused",
            retry_count=1,
            max_retries=3,
            is_retrying=False,
            builder=mock_builder
        )

        assert new_error == "Connection refused"  # Same as before
