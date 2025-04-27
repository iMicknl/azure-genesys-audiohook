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

    async def list(self, active: bool | None = None) -> list[Conversation]:
        """
        List all conversations, optionally filtering by active status.

        :param active: If specified, filters conversations by their active status.
        :return: A list of conversations.
        """
        raise NotImplementedError

    async def get_by_session_id(self, session_id: str) -> Conversation | None:
        raise NotImplementedError

    async def set_active(self, conversation_id: str, active: bool):
        """Set the 'active' status of a conversation."""
        raise NotImplementedError

    async def append_rtt(self, conversation_id: str, rtt: str):
        """Append an RTT entry to the conversation's rtt list."""
        raise NotImplementedError

    async def append_transcript(self, conversation_id: str, item: dict):
        """Append an item to the conversation's transcript list."""
        raise NotImplementedError

    async def close(self):
        """Close the conversation store and release resources."""
        raise NotImplementedError
