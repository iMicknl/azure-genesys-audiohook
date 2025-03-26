import asyncio
import json
import os
from datetime import datetime

from azure.eventhub import EventData, PartitionContext
from azure.eventhub.aio import EventHubConsumerClient
from azure.eventhub.extensions.checkpointstoreblobaio import BlobCheckpointStore
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get Event Hub connection info from environment variables
EVENTHUB_HOSTNAME = os.getenv("EVENTHUB_HOSTNAME")
EVENTHUB_NAME = os.getenv("EVENTHUB_NAME")
EVENTHUB_CONSUMER_GROUP = os.getenv("EVENTHUB_CONSUMER_GROUP", "$Default")


async def process_event(event: EventData):
    """Process an event from the Event Hub based on its type."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        # Parse the event data
        event_body = event.body_as_str()
        event_data = json.loads(event_body)
        event_properties = event.properties

        # Convert binary dictionary to string dictionary
        if event_properties and isinstance(
            next(iter(event_properties.keys()), None), bytes
        ):
            event_properties = {
                k.decode("utf-8"): v.decode("utf-8") if isinstance(v, bytes) else v
                for k, v in event_properties.items()
            }

        session_id = event_properties["session-id"]
        event_type = event_properties["event-type"]

        print(
            f"[{timestamp}] Received event {event_type} - Partition: {event.partition_key}, Seq: {event.sequence_number}"
        )

        # Handle different message types
        if event_type == "azure-genesys-audiohook.session_started":
            print(f"SESSION STARTED: {session_id}")
            print("DATA:")
            print(json.dumps(event_data, indent=2))

        elif event_type == "azure-genesys-audiohook.partial_transcript":
            print(f"PARTIAL TRANSCRIPT: {event_data.get('transcript', '')}")
            # Add specific handling for alert type

        elif event_type == "azure-genesys-audiohook.transcript_available":
            print(f"TRANSCRIPT AVAILABLE: {session_id}")
            print("TRANSCRIPT:")
            print(event_data.get("transcript", {}))
        elif event_type == "azure-genesys-audiohook.recording_available":
            print(f"RECORDING AVAILABLE: {session_id}")
            print("RECORDING:")
            print(json.dumps(event_data, indent=2))
        else:
            print("UNKNOWN TYPE:")
            print(json.dumps(event_data, indent=2))

    except json.JSONDecodeError:
        # Handle non-JSON messages
        print("NON-JSON MESSAGE:")
        print(event.body_as_str())
    except Exception as e:
        print(f"Error processing event: {str(e)}")

    print(f"{'=' * 50}")


async def on_event_batch(partition_context: PartitionContext, events):
    """Process a batch of events from the Event Hub."""
    for event in events:
        await process_event(event)

    # Update the checkpoint
    await partition_context.update_checkpoint()


async def main():
    """Main function to run the Event Hub client."""
    print("Starting Azure Event Hub client...")

    if not EVENTHUB_HOSTNAME or not EVENTHUB_NAME:
        print("Error: Missing required environment variables.")
        print(
            "Please ensure EVENTHUB_NAMESPACE and EVENTHUB_NAME are set in your .env file."
        )
        return

    print(f"Connecting to Event Hub: {EVENTHUB_NAME} in namespace: {EVENTHUB_HOSTNAME}")

    # Create a credential
    credential = DefaultAzureCredential()

    checkpoint_store = BlobCheckpointStore(
        blob_account_url=os.getenv("AZURE_STORAGE_ACCOUNT_URL"),
        container_name=os.getenv(
            "AZURE_STORAGE_ACCOUNT_CONTAINER", "eventhub-checkpointstore"
        ),
        credential=credential,
    )

    # Create an Event Hub consumer client
    fully_qualified_namespace = f"{EVENTHUB_HOSTNAME}"
    client = EventHubConsumerClient(
        fully_qualified_namespace=fully_qualified_namespace,
        eventhub_name=EVENTHUB_NAME,
        consumer_group=EVENTHUB_CONSUMER_GROUP,
        credential=credential,
        # checkpoint_store=checkpoint_store,
    )

    try:
        # Start receiving events
        print("Listening for events. Press Ctrl+C to exit.")
        async with client:
            await client.receive_batch(
                on_event_batch=on_event_batch,
                starting_position="@latest",  # Start from the end of the partition (-1) or use @latest
            )
    except KeyboardInterrupt:
        print("Client stopped by user.")
    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
