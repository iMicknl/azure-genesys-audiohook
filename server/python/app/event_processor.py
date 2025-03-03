"""Event Processor for Azure Event Hub

This module provides a class for batch processing events to be sent to Azure Event Hub.
It efficiently handles many concurrent connections by queuing events and sending them in batches.
"""

import asyncio
import logging
from typing import Optional

from azure.eventhub import EventData
from azure.eventhub.aio import EventHubProducerClient


class EventProcessor:
    """Class to manage event batching for Azure Event Hub

    This class implements a reliable batch processing system for Azure Event Hub events.
    It queues events and sends them in regular intervals to optimize throughput while
    minimizing latency.

    Attributes:
        producer_client: The Azure Event Hub producer client
        batch_interval: How often to send batches (in seconds)
        event_queue: Queue of events waiting to be sent
        lock: Async lock to protect the event queue during concurrent access
        batch_task: Task handling the batch processing
        running: Flag indicating if the processor is running
    """

    def __init__(
        self,
        producer_client: Optional[EventHubProducerClient] = None,
        batch_interval: float = 0.5,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize the event processor.

        Args:
            producer_client: Azure Event Hub producer client
            batch_interval: How often to send batches in seconds
            logger: Logger instance to use for logging
        """
        self.producer_client = producer_client
        self.batch_interval = batch_interval
        self.event_queue: list[EventData] = []
        self.lock = asyncio.Lock()
        self.batch_task = None
        self.running = False
        self.logger = logger or logging.getLogger(__name__)

    async def start(self):
        """Start the batch processing task"""
        if not self.running:
            self.logger.info("Starting event batch processor")
            self.running = True
            self.batch_task = asyncio.create_task(self._process_batch())

    async def stop(self):
        """Stop the batch processing task and send any remaining events"""
        if self.running:
            self.logger.info("Stopping event batch processor")
            self.running = False
            if self.batch_task:
                await self.batch_task
            # Send any remaining events
            await self._send_batch()

    async def add_event(self, event_data: EventData):
        """Add an event to the queue

        Args:
            event_data: The event to add to the queue
        """
        async with self.lock:
            self.event_queue.append(event_data)
            self.logger.debug(
                f"Event added to queue (queue size: {len(self.event_queue)})"
            )

    async def _process_batch(self):
        """Process batches at regular intervals"""
        self.logger.info(
            f"Batch processing started with interval: {self.batch_interval}s"
        )
        while self.running:
            await asyncio.sleep(self.batch_interval)
            await self._send_batch()

    async def _send_batch(self):
        """Send the current batch of events"""
        if not self.producer_client:
            self.logger.debug("No producer client available, skipping batch")
            return

        async with self.lock:
            queue_size = len(self.event_queue)
            if queue_size == 0:
                return

            self.logger.debug(f"Sending batch of {queue_size} events")
            try:
                event_data_batch = await self.producer_client.create_batch()
                events_to_send = []
                events_not_sent = []

                # Add events to batch until full
                for event in self.event_queue:
                    if event_data_batch.add(event):
                        events_to_send.append(event)
                    else:
                        # Batch is full, send it and create a new one
                        self.logger.debug(
                            f"Batch full, sending {len(event_data_batch)} events"
                        )
                        await self.producer_client.send_batch(event_data_batch)

                        # Create a new batch for remaining events
                        event_data_batch = await self.producer_client.create_batch()
                        if event_data_batch.add(event):
                            events_to_send.append(event)
                        else:
                            # If event is too large even for an empty batch
                            self.logger.warning("Event too large for batch, skipping")
                            events_not_sent.append(event)

                # Send the final batch if it has events
                if len(event_data_batch) > 0:
                    self.logger.debug(
                        f"Sending final batch of {len(event_data_batch)} events"
                    )
                    await self.producer_client.send_batch(event_data_batch)

                # Replace the queue with only events that weren't sent
                self.event_queue = events_not_sent

                if events_not_sent:
                    self.logger.warning(
                        f"{len(events_not_sent)} events could not be sent"
                    )

                self.logger.debug(
                    f"Batch sent successfully. Sent: {len(events_to_send)}, Remaining: {len(events_not_sent)}"
                )

            except Exception as e:
                # Log the error but don't remove events from queue so they can be retried
                self.logger.error(f"Error sending event batch: {e}", exc_info=True)
