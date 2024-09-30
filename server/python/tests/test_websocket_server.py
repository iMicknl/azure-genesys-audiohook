import pytest

from app.websocket_server import WebsocketServer


@pytest.fixture
def app():
    """Create a test client for the app. See https://quart.palletsprojects.com/en/latest/how_to_guides/testing.html#testing"""
    server = WebsocketServer()
    app = server.app.test_client()

    return app


@pytest.mark.asyncio
async def test_health_check(app):
    """Test health check endpoint"""
    response = await app.get("/")

    assert response.status_code == 200
