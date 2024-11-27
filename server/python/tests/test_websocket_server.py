import pytest
import os
from app.websocket_server import WebsocketServer


os.environ["WEBSOCKET_SERVER_API_KEY"] = "SGVsbG8sIEkgYW0gdGhlIEFQSSBrZXkh"
os.environ["WEBSOCKET_SERVER_CLIENT_SECRET"] = (
    "TXlTdXBlclNlY3JldEtleVRlbGxOby0xITJAMyM0JDU="
)


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
    assert (
        await response.data
        == b'{"client_sessions":{},"connected_clients":0,"status":"online"}\n'
    )


@pytest.mark.asyncio
async def test_health_check_valid_json(app):
    """Test if health check endpoint is valid JSON"""
    response = await app.get("/")

    # Check if response data is valid JSON
    data = await response.get_json()

    assert data is not None
    assert data["status"] == "online"
    assert data["connected_clients"] == 0


@pytest.mark.asyncio
async def test_invalid_route(app):
    """Test invalid route"""
    response = await app.get("/invalid")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ws_invalid_api_key(app):
    """Test websocket connection with invalid API key"""

    headers = {
        "X-Api-Key": "invalid_key",
        "Audiohook-Session-Id": "test_session",
        "Audiohook-Correlation-Id": "test_correlation",
        "Signature-Input": "test_signature_input",
        "Signature": "test_signature",
    }

    async with app.websocket("/ws", headers=headers) as ws:
        response = await ws.receive_json()

        assert response["type"] == "disconnect"
        assert response["parameters"]["reason"] == "unauthorized"
        assert response["parameters"]["info"] == "Invalid API Key"


@pytest.mark.asyncio
async def test_ws_valid_connection(app):
    """Test valid websocket connection"""
    headers = {
        "X-Api-Key": os.getenv("WEBSOCKET_SERVER_API_KEY"),
        "Audiohook-Session-Id": "e160e428-53e2-487c-977d-96989bf5c99d",
        "Audiohook-Correlation-Id": "test_correlation",
        "Signature-Input": "test_signature_input",
        "Signature": "test_signature",
    }
    async with app.websocket("/ws", headers=headers) as ws:
        # Open Transaction
        # https://developer.genesys.cloud/devapps/audiohook/session-walkthrough#open-transaction
        await ws.send_json(
            {
                "version": "2",
                "type": "open",
                "seq": 1,
                "serverseq": 0,
                "id": "e160e428-53e2-487c-977d-96989bf5c99d",
                "position": "PT0S",
                "parameters": {
                    "organizationId": "d7934305-0972-4844-938e-9060eef73d05",
                    "conversationId": "090eaa2f-72fa-480a-83e0-8667ff89c0ec",
                    "participant": {
                        "id": "883efee8-3d6c-4537-b500-6d7ca4b92fa0",
                        "ani": "+1-555-555-1234",
                        "aniName": "John Doe",
                        "dnis": "+1-800-555-6789",
                    },
                    "media": [
                        {
                            "type": "audio",
                            "format": "PCMU",
                            "channels": ["external", "internal"],
                            "rate": 8000,
                        },
                        {
                            "type": "audio",
                            "format": "PCMU",
                            "channels": ["external"],
                            "rate": 8000,
                        },
                        {
                            "type": "audio",
                            "format": "PCMU",
                            "channels": ["internal"],
                            "rate": 8000,
                        },
                    ],
                    "language": "en-US",
                },
            }
        )

        response = await ws.receive_json()

        assert response["type"] == "opened"
