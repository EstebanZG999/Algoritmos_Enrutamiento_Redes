# Esquema y utilidades de mensajes
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Any
import uuid

Proto = Literal["dijkstra", "flooding", "lsr", "dvr"]
Type  = Literal["message", "echo", "info", "hello"]

class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    proto: Proto
    type:  Type
    id:    str = Field(default_factory=lambda: str(uuid.uuid4()))

    from_: str = Field(alias="from")
    to:    str
    ttl:   int = Field(ge=0, le=64, default=8)
    headers: list[dict[str, Any]] = []
    payload: dict[str, Any] | str

    def dec(self) -> "Message":
        """Devuelve una copia con TTL decrementado (sin bajar de 0)."""
        return self.model_copy(update={"ttl": max(0, self.ttl - 1)})

    def as_wire(self) -> dict:
        """Dict serializable con claves EXACTAS (incluye 'from')."""
        return self.model_dump(by_name=True)
