import json
import os
from typing import Any, Dict, Optional

from app.utils.identity import get_azure_credential_async
from azure.eventhub import EventData
from azure.eventhub.aio import EventHubProducerClient


class EventPublisher:
    """
    Abstraction for publishing events to Azure Event Hub.
    Handles connection, sending, and (future) batching/queueing.
    """

    def __init__(self):
        if fully_qualified_namespace := os.getenv(
            "AZURE_EVENT_HUB_FULLY_QUALIFIED_NAMESPACE"
        ):
            self.producer_client = EventHubProducerClient(
                fully_qualified_namespace=fully_qualified_namespace,
                eventhub_name=os.environ["AZURE_EVENT_HUB_NAME"],
                credential=get_azure_credential_async(),
            )
        elif connection_string := os.getenv("AZURE_EVENT_HUB_CONNECTION_STRING"):
            self.producer_client = EventHubProducerClient.from_connection_string(
                conn_str=connection_string,
                eventhub_name=os.environ["AZURE_EVENT_HUB_NAME"],
            )
        else:
            raise RuntimeError(
                "Azure Event Hub configuration not found in environment variables."
            )

    async def close(self):
        if self.producer_client:
            await self.producer_client.close()

    async def send_event(
        self,
        event_type: str,
        conversation_id: str,
        message: Dict[str, Any],
        properties: Optional[Dict[str, str]] = None,
    ):
        event_data_batch = await self.producer_client.create_batch()
        event_data = EventData(json.dumps(message))
        event_data.properties = {
            "event-type": event_type,
            "conversation-id": conversation_id,
        }
        if properties:
            event_data.properties.update(properties)

        event_data_batch.add(event_data)

        # TODO Implement batching and queueing
        await self.producer_client.send_batch(event_data_batch)
