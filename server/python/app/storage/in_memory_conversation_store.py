from ..models import Conversation
from .base_conversation_store import ConversationStore


class InMemoryConversationStore(ConversationStore):
    """
    In-memory implementation of the ConversationStore interface.
    This class is used for testing and development purposes.
    It stores conversations in a dictionary.
    """

    def __init__(self):
        self._store = {}

    async def get(self, conversation_id: str) -> Conversation | None:
        return self._store.get(conversation_id)

    async def set(self, conversation: Conversation):
        self._store[conversation.id] = conversation

    async def delete(self, conversation_id: str):
        if conversation_id in self._store:
            del self._store[conversation_id]

    async def list(self, active: bool | None = None) -> list[Conversation]:
        if active is None:
            return list(self._store.values())
        return [
            c for c in self._store.values() if getattr(c, "active", False) == active
        ]

    async def get_by_session_id(self, session_id: str) -> Conversation | None:
        for conversation in self._store.values():
            if conversation.session_id == session_id:
                return conversation
        return None

    async def set_active(self, conversation_id: str, active: bool):
        conversation = await self.get(conversation_id)
        if conversation:
            conversation.active = active
            await self.set(conversation)

    async def append_rtt(self, conversation_id: str, rtt: str):
        conversation = await self.get(conversation_id)
        if conversation:
            conversation.rtt.append(rtt)
            await self.set(conversation)

    async def append_transcript(self, conversation_id: str, item: dict):
        conversation = await self.get(conversation_id)
        if conversation:
            conversation.transcript.append(item)
            await self.set(conversation)
