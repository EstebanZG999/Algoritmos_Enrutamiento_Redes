# src/routerlab/core/messages.py
# Esquema y utilidades de mensajes

from typing import Literal, Any, Optional

# Compatibilidad Pydantic v1/v2
try:
    from pydantic import BaseModel, Field, ConfigDict  # v2
    _IS_PD_V2 = True
except Exception:  # pragma: no cover
    from pydantic import BaseModel, Field              # v1
    _IS_PD_V2 = False

import uuid, time

Proto = Literal["dijkstra", "flooding", "lsr", "dvr"]
Type  = Literal["message", "echo", "info", "hello"]


class Message(BaseModel):
    """
    Envelope canónico del lab:
      proto, type, id, from, origin, to, ttl, headers[], payload, via?
    """
    if _IS_PD_V2:
        model_config = ConfigDict(populate_by_name=True)
    else:
        class Config:                                     # v1
            allow_population_by_field_name = True

    proto: Proto
    type:  Type
    id:    str = Field(default_factory=lambda: str(uuid.uuid4()))

    # 'from' es palabra reservada en Python; usamos from_ y alias
    from_: str = Field(alias="from")

    # Emisor original; permanece constante en todo el trayecto
    origin: Optional[str] = None

    # Destino lógico (unicast) o "*" (broadcast)
    to:    str = "*"

    # TTL acotado
    ttl:   int = Field(ge=0, le=64, default=8)

    # ¡Evitar default mutable! Usar default_factory=list
    headers: list[dict[str, Any]] = Field(default_factory=list)

    # Carga útil: puede ser JSON (dict) o texto
    payload: dict[str, Any] | str

    # Hop anterior (opcional, útil para anti-eco)
    via: Optional[str] = None

    def dec(self) -> "Message":
        """Copia con TTL decrementado (no baja de 0)."""
        new_ttl = max(0, self.ttl - 1)
        if _IS_PD_V2:
            return self.model_copy(update={"ttl": new_ttl})
        else:
            return self.copy(update={"ttl": new_ttl})

    def with_origin(self) -> "Message":
        """Garantiza que origin está seteado (si viene None)."""
        if self.origin is None:
            if _IS_PD_V2:
                return self.model_copy(update={"origin": self.from_})
            else:
                return self.copy(update={"origin": self.from_})
        return self

    def as_wire(self) -> dict:
        """Dict serializable con alias EXACTOS (incluye 'from')."""
        if _IS_PD_V2:
            return self.model_dump(by_alias=True)
        else:
            return self.dict(by_alias=True)


# -------------------------
# Helpers de construcción
# -------------------------

def make_id() -> str:
    return str(uuid.uuid4())


def make_data(proto: Proto, src: str, to: str, payload: Any, ttl: int = 8) -> Message:
    """
    Crea un mensaje de aplicación (DATA).
    Usa 'src' como from y origin; el forwarder puede reasignar 'from' en cada salto.
    """
    msg = Message(
        proto=proto,
        type="message",
        from_=src,
        origin=src,
        to=to,
        ttl=ttl,
        payload=payload,
    )
    return msg


def make_lsa(src: str, entry: dict[str, dict[str, int]], seq: int, ttl: int = 8, age: int = 30) -> Message:
    """
    Crea un LSA (INFO) para LSR.
    entry: p.ej., {"N7": {"N1": 4, "N10": 3, "N11": 11}}
    Headers:
      - seq: número monotónico por 'origin'
      - age: segundos sugeridos de vida
      - ts : timestamp de emisión (diagnóstico/expiración)
    """
    headers = [{"seq": int(seq)}, {"age": int(age)}, {"ts": int(time.time())}]
    msg = Message(
        proto="lsr",
        type="info",
        from_=src,
        origin=src,
        to="*",
        ttl=ttl,
        headers=headers,
        payload={"lsdb_entry": entry},
    )
    return msg


# -------------------------
# Helpers de headers
# -------------------------

def header_get(msg_or_headers: Message | list[dict[str, Any]], key: str, default=None):
    """
    Obtiene un header por clave desde Message.headers (lista de dicts).
    """
    headers = msg_or_headers.headers if isinstance(msg_or_headers, Message) else msg_or_headers
    for h in headers:
        if key in h:
            return h[key]
    return default


def header_put(msg: Message, key: str, value: Any) -> Message:
    """
    Añade/reemplaza un header (inmutable: devuelve nueva instancia en v2/v1).
    """
    new_headers = [dict(h) for h in msg.headers]
    # reemplazar si existe
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


# -------------------------
# Normalización rápida
# -------------------------

def to_wire_dict(msg: Message) -> dict:
    """
    Dump canónico (alias por nombre) para enviar por el driver.
    """
    return msg.as_wire()
