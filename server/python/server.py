import logging
import os

from app.websocket_server import WebsocketServer
from dotenv import find_dotenv, load_dotenv

LOGGER: logging.Logger = logging.getLogger(__name__)

# Set logging level based on environment variables
if os.getenv("DEBUG_MODE") == "true":
    logging.basicConfig(level=logging.DEBUG)
    LOGGER.info("Starting server in debug mode")
else:
    logging.basicConfig(level=logging.WARNING)

# Run development server when running this script directly.
# For production it is recommended that Quart will be run using Hypercorn or an alternative ASGI server.
if __name__ == "__main__":
    load_dotenv(find_dotenv())
    server = WebsocketServer()
    server.app.run()
else:
    server = WebsocketServer()
    app = server.app
