from ..models import Conversation


class ConversationStore:
    """
    Interface for storing and retrieving conversations.
    This is an abstract class that defines the methods for
    getting, setting, deleting, and listing conversations.
    """

    async def get(self, conversation_id: str) -> Conversation | None:
        raise NotImplementedError

    async def set(self, conversation: Conversation):
        raise NotImplementedError

    async def delete(self, conversation_id: str):
        raise NotImplementedError

    async def list(self) -> list[Conversation]:
        raise NotImplementedError

    async def get_by_session_id(self, session_id: str) -> Conversation | None:
        raise NotImplementedError
