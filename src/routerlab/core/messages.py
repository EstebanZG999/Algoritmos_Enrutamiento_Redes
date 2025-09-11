# src/routerlab/core/messages.py
from typing import Literal, Any, Optional

# Compatibilidad Pydantic v1/v2
try:
    from pydantic import BaseModel, Field, ConfigDict, field_validator  # v2
    _IS_PD_V2 = True
except Exception:  # pragma: no cover
    from pydantic import BaseModel, Field, validator                     # v1
    _IS_PD_V2 = False

import uuid, time

Proto = Literal["dijkstra", "flooding", "lsr", "dvr"]
Type  = Literal["message", "echo", "info", "hello", "lsp"]

def _coerce_headers(value):
    if value is None:
        return []
    if isinstance(value, list):
        # asegurarnos de que cada item sea dict
        return [dict(x) if isinstance(x, dict) else {"value": x} for x in value]
    if isinstance(value, dict):
        return [value]
    # cualquier otro tipo: vaciamos
    return []

class Message(BaseModel):
    """
    Envelope canónico del lab:
      proto, type, id, from, origin, to, ttl, headers[], payload, via?
    """
    if _IS_PD_V2:
        model_config = ConfigDict(populate_by_name=True)
    else:
        class Config:
            allow_population_by_field_name = True

    proto: Proto
    type:  Type
    id:    str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_: str = Field(alias="from")
    origin: Optional[str] = None
    to:    str = "*"
    ttl:   int = Field(ge=0, le=64, default=8)

    # ¡importante! default_factory + normalización
    headers: list[dict[str, Any]] = Field(default_factory=list)

    payload: dict[str, Any] | str
    via: Optional[str] = None

    # -------- Normalización de headers (v2 y v1) ----------
    if _IS_PD_V2:
        @field_validator("headers", mode="before")
        @classmethod
        def _normalize_headers_v2(cls, v):
            return _coerce_headers(v)
    else:
        @validator("headers", pre=True, always=True)
        def _normalize_headers_v1(cls, v):
            return _coerce_headers(v)

    def dec(self) -> "Message":
        new_ttl = max(0, self.ttl - 1)
        if _IS_PD_V2:
            return self.model_copy(update={"ttl": new_ttl})
        else:
            return self.copy(update={"ttl": new_ttl})

    def with_origin(self) -> "Message":
        if self.origin is None:
            if _IS_PD_V2:
                return self.model_copy(update={"origin": self.from_})
            else:
                return self.copy(update={"origin": self.from_})
        return self

    def as_wire(self) -> dict:
        if _IS_PD_V2:
            return self.model_dump(by_alias=True)
        else:
            return self.dict(by_alias=True)

# Helpers (si ya los tenías, mantén los tuyos)
def make_id() -> str:
    return str(uuid.uuid4())

def make_data(proto: Proto, src: str, to: str, payload: Any, ttl: int = 8) -> Message:
    return Message(proto=proto, type="message", from_=src, origin=src, to=to, ttl=ttl, payload=payload)

def make_lsa(src: str, entry: dict[str, dict[str, int]], seq: int, ttl: int = 8, age: int = 30) -> Message:
    headers = [{"seq": int(seq)}, {"age": int(age)}, {"ts": int(time.time())}]
    return Message(proto="lsr", type="info", from_=src, origin=src, to="*", ttl=ttl,
                   headers=headers, payload={"lsdb_entry": entry})

def header_get(msg_or_headers: Message | list[dict[str, Any]], key: str, default=None):
    headers = msg_or_headers.headers if isinstance(msg_or_headers, Message) else msg_or_headers
    for h in headers:
        if key in h: return h[key]
    return default

def header_put(msg: Message, key: str, value: Any) -> Message:
    new_headers = [dict(h) for h in msg.headers]
    for h in new_headers:
        if key in h:
            h[key] = value
            break
    else:
        new_headers.append({key: value})
    if _IS_PD_V2:
        return msg.model_copy(update={"headers": new_headers})
    else:
        return msg.copy(update={"headers": new_headers})

def to_wire_dict(msg: Message) -> dict:
    return msg.as_wire()
