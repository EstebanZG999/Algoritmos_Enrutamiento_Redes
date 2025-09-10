# src/routerlab/net/redis_driver.py
import os, json, asyncio, uuid
from typing import AsyncIterator, Dict, Any
from redis.asyncio import Redis
from routerlab.net.transport import Transport
from dotenv import load_dotenv

class RedisDriver(Transport):
    """
    Pub/Sub por canal: cada nodo escucha su canal (names-redis-11.txt).
    send(dest) = PUBLISH al canal del destino con payload JSON.
    """
    def __init__(self, node: str, names_path: str):
        load_dotenv()

        self._node = node
        self.names_path = names_path

        # Cargar mapa de canales
        self._names = self._load_names(self.names_path)
        self._rev = {v: k for k, v in self._names.items()}

        # Conexión (host/port/db)
        url = os.getenv("REDIS_URL")
        host = os.getenv("REDIS_HOST", "127.0.0.1")
        port = int(os.getenv("REDIS_PORT", "6379"))
        db   = int(os.getenv("REDIS_DB",   "0"))
        password = os.getenv("REDIS_PASSWORD")
        tls = os.getenv("REDIS_TLS", "0") == "1"

        if url:
            self._r = Redis.from_url(url, decode_responses=False, ssl=tls)
        else:
            self._r = Redis(
                host=host, port=port, db=db, password=password,
                ssl=tls, decode_responses=False
            )

        # Canal propio de escucha
        self._my_channel = self._names.get(self._node)
        if not self._my_channel:
            raise RuntimeError(f"No hay canal para nodo {self._node} en {names_path}")

    def _load_names(self, path: str) -> dict[str, str]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("type") == "names", "names-redis inválido: falta type=names"
        return data["config"]

    def me(self) -> str:
        return self._node

    async def run(self) -> AsyncIterator[Dict[str, Any]]:
        pubsub = self._r.pubsub()
        await pubsub.subscribe(self._my_channel)

        async for msg in pubsub.listen():
            # Estructura: {'type':'message'|..., 'channel': b'...', 'data': b'...'|str}
            if msg.get("type") != "message":
                continue

            channel = msg.get("channel")
            if isinstance(channel, (bytes, bytearray)):
                channel = channel.decode("utf-8", "ignore")

            data = msg.get("data")
            raw: Dict[str, Any] | None = None

            # --- Intentar decodificar como JSON ---
            if isinstance(data, (bytes, bytearray)):
                s = data.decode("utf-8", "ignore")
            elif isinstance(data, str):
                s = data
            else:
                s = None

            if s is not None:
                try:
                    raw = json.loads(s)  # JSON válido
                except Exception:
                    # --- Fallback: string crudo -> envolver en sobre canónico ---
                    sender = self._rev.get(channel) or self._node or "unknown"
                    raw = {
                        "proto": "flooding",
                        "type": "message",
                        "id": str(uuid.uuid4()),
                        "from": sender,
                        "origin": sender,
                        "to": "*",
                        "ttl": 8,
                        "headers": [],
                        "payload": s,
                        "via": sender,
                    }

            if not isinstance(raw, dict):
                continue

            # --- Normalizaciones mínimas (robustez entre grupos) ---
            raw.setdefault("from", raw.get("from") or self._node)
            raw.setdefault("origin", raw.get("origin") or raw["from"])
            raw.setdefault("to", raw.get("to") or "*")
            raw.setdefault("ttl", raw.get("ttl") or 8)
            # headers puede venir como {}, None, etc. -> normalizar a lista
            hdrs = raw.get("headers")
            if hdrs is None:
                raw["headers"] = []
            elif isinstance(hdrs, dict):
                raw["headers"] = [hdrs]
            elif not isinstance(hdrs, list):
                raw["headers"] = []

            raw.setdefault("proto", raw.get("proto") or "flooding")
            raw.setdefault("type",  raw.get("type")  or "message")

            # Vía: si no viene, usar el dueño del canal o 'from'
            raw.setdefault("via", self._rev.get(channel) or raw.get("from"))

            yield raw

    async def send(self, to: str, message: Dict[str, Any]) -> None:
        channel = self._names.get(to)
        if not channel:
            return
        try:
            wire = json.dumps(message, separators=(",", ":")).encode("utf-8")
            await self._r.publish(channel, wire)
        except Exception:
            return
