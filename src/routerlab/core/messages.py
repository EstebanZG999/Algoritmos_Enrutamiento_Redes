# src/routerlab/core/messages.py
from typing import Literal, Optional
try:
    from pydantic import BaseModel, Field, ConfigDict  # v2
    _IS_PD_V2 = True
except Exception:
    from pydantic import BaseModel, Field              # v1
    _IS_PD_V2 = False

import uuid

# Protocolos y tipos válidos
Proto = Literal["lsr", "flooding"]
Type  = Literal["message", "hello"]

class Message(BaseModel):
    """
    Formato canónico del laboratorio:
      {type: "message", from: nodoX, to: nodoY, hops: costo, proto, id, ttl}
      {type: "hello",   from: nodoX, metric: costo}
    Notas:
      - "hello" → heartbeat para mantener vecinos vivos.
      - "message" → describe adyacencia directa (from,to,hops).
    """
    if _IS_PD_V2:
        model_config = ConfigDict(populate_by_name=True)
    else:
        class Config:
            allow_population_by_field_name = True

    proto: Proto
    type:  Type
    id:    str = Field(default_factory=lambda: str(uuid.uuid4()))

    # Campos de topología (para message)
    from_: str = Field(alias="from")
    to: str
    hops: Optional[float] = None  # solo aplica si type="message"

    # Control de flooding
    ttl: int = Field(ge=0, le=64, default=8)

    # Opcionales
    origin: Optional[str] = None
    via: Optional[str] = None

    def dec(self) -> "Message":
        """Devuelve copia con TTL-1 (sin ir negativo)."""
        new_ttl = max(0, self.ttl - 1)
        if _IS_PD_V2:
            return self.model_copy(update={"ttl": new_ttl})
        else:
            return self.copy(update={"ttl": new_ttl})

    def as_wire(self) -> dict:
        """Serializa a dict respetando alias."""
        if _IS_PD_V2:
            return self.model_dump(by_alias=True)
        else:
            return self.dict(by_alias=True)

# -----------------------
# Helpers
# -----------------------
def make_id() -> str:
    return str(uuid.uuid4())

def make_hello() -> Message:
    """
    Construye un paquete hello minimalista:
    {type:"hello"}
    """
    return {"type": "hello"}



def make_message(src: str, dst: str, hops: float, ttl: int = 8) -> Message:
    """
    Construye un paquete de adyacencia en formato:
      {type:"message", from:src, to:dst, hops:costo}
    """
    return Message(proto="lsr", type="message", from_=src, to=dst,
                   hops=float(hops), ttl=ttl, origin=src)
