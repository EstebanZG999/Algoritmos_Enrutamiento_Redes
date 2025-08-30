from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any

class Transport(ABC):
    @abstractmethod
    async def run(self) -> AsyncIterator[Dict[str, Any]]:
        """Itera mensajes recibidos como dicts parseables a Message."""
        ...

    @abstractmethod
    async def send(self, to: str, message: Dict[str, Any]) -> None:
        """Envía 'message' (dict) hacia el identificador 'to' (node-id/JID)."""
        ...

    @abstractmethod
    def me(self) -> str:
        """Identificador local (node-id o JID/resource)."""
        ...
