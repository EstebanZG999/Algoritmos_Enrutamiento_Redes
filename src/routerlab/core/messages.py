# src/routerlab/core/messages.py
# Esquema y utilidades de mensajes
from pydantic import BaseModel, Field
from typing import Literal, Any, Optional
import uuid

# Detectar si es Pydantic v2 o v1
try:
    from pydantic import BaseModel, Field, ConfigDict  # v2
    _IS_PD_V2 = True
except Exception:
    from pydantic import BaseModel, Field              # v1
    _IS_PD_V2 = False

Proto = Literal["dijkstra", "flooding", "lsr", "dvr"]
Type  = Literal["message", "echo", "info", "hello"]

class Message(BaseModel):
    if _IS_PD_V2:
        model_config = ConfigDict(populate_by_name=True)  # v2 OK
    else:
        class Config:                                     # v1 compat
            allow_population_by_field_name = True

    # Campos
    proto: Proto
    type:  Type
    id:    str = Field(default_factory=lambda: str(uuid.uuid4()))
    # salto previo
    from_: str = Field(alias="from")
    # origin es el emisor original no cambia en cada salto
    origin: Optional[str] = None

    to:    str = "*"

    ttl:   int = Field(ge=0, le=64, default=8)
    headers: list[dict[str, Any]] = []
    payload: dict[str, Any] | str
    via: Optional[str] = None

    def dec(self) -> "Message":
        """Copia con TTL decrementado (no baja de 0). Compatible v1/v2."""
        new_ttl = max(0, self.ttl - 1)
        if _IS_PD_V2:
            return self.model_copy(update={"ttl": new_ttl})  # v2
        else:
            return self.copy(update={"ttl": new_ttl})        # v1

    def as_wire(self) -> dict:
        """Dict serializable con alias EXACTOS (incluye 'from')."""
        if _IS_PD_V2:
            return self.model_dump(by_alias=True)  # v2
        else:
            return self.dict(by_alias=True)        # v1
