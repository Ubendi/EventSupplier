"""
Pytest configuration and shared fixtures for mqtt_interface_app tests.
"""
import pytest
import logging
from unittest.mock import AsyncMock, MagicMock


# Configure logging for tests
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


@pytest.fixture(autouse=True)
def configure_logging():
    """Configure logging for all tests to ensure logs are captured."""
    # Get the vlc_main logger and ensure it propagates
    logger = logging.getLogger("vlc_interface.vlc_main")
    logger.setLevel(logging.INFO)
    # Ensure it has a handler that propagates to root
    if not logger.handlers:
        logger.propagate = True


@pytest.fixture
def mock_mqtt_interface():
    """Mock MQTTInterface with async publish_event method."""
    mock = MagicMock()
    mock.publish_event = AsyncMock(return_value=MagicMock(status="success"))
    return mock


@pytest.fixture
def mock_listener():
    """Mock VLCListener with controlled status responses."""
    mock = MagicMock()
    return mock


@pytest.fixture
def mock_builder():
    """Mock VLCEventBuilder."""
    mock = MagicMock()
    return mock


@pytest.fixture
def mock_emitter():
    """Mock VLCEmitter."""
    mock = MagicMock()
    mock.send = MagicMock(return_value=MagicMock(message="test_message"))
    return mock


@pytest.fixture
def mock_status_ok():
    """Mock VLC status with OK state and media."""
    mock = MagicMock()
    mock.status = "ok"
    mock.payload = {
        "information": {
            "category": {
                "meta": {"filename": "test_movie.mp4"}
            }
        },
        "position": 10.5
    }
    mock.error = None
    return mock


@pytest.fixture
def mock_status_error():
    """Mock VLC status with error state."""
    mock = MagicMock()
    mock.status = "error"
    mock.payload = {}
    mock.error = "Connection refused"
    return mock
