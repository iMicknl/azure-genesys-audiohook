"""Database utilities for the server."""

import os
from typing import Any

from azure.cosmos.aio import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from .identity import get_azure_credential_async
from .models import ClientSession


class Database:
    """Database class for Azure Cosmos DB operations."""

    def __init__(self):
        """Initialize the database client."""
        self.client = None
        self.database = None
        self.container = None

    async def create_connection(self):
        """Create connection to Cosmos DB."""
        if endpoint := os.getenv("AZURE_COSMOS_ENDPOINT"):
            self.client = CosmosClient(
                url=endpoint,
                credential=get_azure_credential_async(),
            )
        elif connection_string := os.getenv("AZURE_COSMOS_CONNECTION_STRING"):
            self.client = CosmosClient.from_connection_string(connection_string)

        if self.client:
            database_name = os.getenv("AZURE_COSMOS_DATABASE", "audiohook")
            container_name = os.getenv("AZURE_COSMOS_CONTAINER", "sessions")

            self.database = self.client.get_database_client(database_name)
            self.container = self.database.get_container_client(container_name)

    async def close_connection(self):
        """Close the database connection."""
        if self.client:
            await self.client.close()

    async def save_session(self, conversation_id: str, session: ClientSession) -> None:
        """Save a client session to the database."""
        if not self.container:
            return

        # Clean the session object (remove non-serializable fields)
        clean_session = {
            "id": conversation_id,
            "ani": session.ani,
            "ani_name": session.ani_name,
            "dnis": session.dnis,
            "conversation_id": session.conversation_id,
            "client_seq": session.client_seq,
            "server_seq": session.server_seq,
            "rtt": session.rtt,
            "last_rtt": session.last_rtt,
            "media": session.media,
            "transcript": session.transcript,
            "event_state": session.event_state,
            "summary": session.summary,
            "ai_insights": session.ai_insights,
            "start_streaming": session.start_streaming,
        }

        await self.container.upsert_item(clean_session)

    async def get_session(self, conversation_id: str) -> dict[str, Any] | None:
        """Get a client session from the database."""
        if not self.container:
            return None

        try:
            item = await self.container.read_item(
                item=conversation_id,
                partition_key=conversation_id,
            )
            return item
        except CosmosResourceNotFoundError:
            return None
