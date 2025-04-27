import os

from azure.cosmos import PartitionKey
from azure.cosmos.aio import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from ..models import Conversation
from ..utils.identity import get_azure_credential_async
from .base_conversation_store import ConversationStore


class CosmosDBConversationStore(ConversationStore):
    """
    CosmosDB implementation of the ConversationStore interface.
    """

    def __init__(self):
        if endpoint := os.getenv("AZURE_COSMOSDB_ENDPOINT"):
            self.client = CosmosClient(
                url=endpoint,
                credential=get_azure_credential_async(),
            )
        elif connection_string := os.getenv("AZURE_COSMOSDB_CONNECTION_STRING"):
            self.client = CosmosClient.from_connection_string(connection_string)

        database_name = os.environ.get("AZURE_COSMOSDB_DATABASE", "audiohook")
        container_name = os.environ.get("AZURE_COSMOSDB_CONTAINER", "conversations")

        self.database_name = database_name
        self.container_name = container_name
        self._db = None
        self._container = None

    async def _get_container(self):
        if not self._container:
            if not self._db:
                self._db = await self.client.create_database_if_not_exists(
                    self.database_name
                )
            self._container = await self._db.create_container_if_not_exists(
                id=self.container_name,
                partition_key=PartitionKey(path="/id"),
                indexing_policy={
                    "indexingMode": "consistent",
                    "includedPaths": [
                        {"path": "/session_id/?"},
                        {"path": "/active/?"},
                        {"path": "/ani/?"},
                        {"path": "/ani_name/?"},
                        {"path": "/dnis/?"},
                    ],
                    "excludedPaths": [{"path": "/*"}],
                },
            )
        return self._container

    async def get(self, conversation_id: str) -> Conversation | None:
        container = await self._get_container()
        try:
            item = await container.read_item(
                conversation_id, partition_key=conversation_id
            )
            return Conversation(**item)
        except CosmosResourceNotFoundError:
            return None

    async def set(self, conversation: Conversation):
        container = await self._get_container()
        data = conversation.model_dump()
        await container.upsert_item(data)

    async def delete(self, conversation_id: str) -> None:
        container = await self._get_container()
        await container.delete_item(conversation_id, partition_key=conversation_id)

    async def list(self) -> list[Conversation]:
        container = await self._get_container()
        query = "SELECT * FROM c"
        items = container.query_items(query)
        return [Conversation(**item) async for item in items]

    async def get_by_session_id(self, session_id: str) -> Conversation | None:
        container = await self._get_container()
        query = "SELECT * FROM c WHERE c.session_id = @session_id"
        params = [{"name": "@session_id", "value": session_id}]
        items = container.query_items(query, parameters=params)
        async for item in items:
            return Conversation(**item)
        return None
