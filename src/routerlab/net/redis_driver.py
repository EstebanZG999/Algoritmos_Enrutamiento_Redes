# Transporte Redis (Pub/Sub) para RouterLab
import os, json, asyncio
from typing import AsyncIterator, Dict, Any
from redis.asyncio import Redis
from routerlab.net.transport import Transport


class RedisDriver(Transport):
    """
    Pub/Sub por canal: cada nodo escucha su canal (names-redis.json).
    send(dest) = PUBLISH a canal del destino con payload JSON.
    """
    def __init__(self, node: str, names_path: str):
        self._node = node
        self._names = self._load_names(names_path)

        # Conexion (host/port/db opcional por entorno)
        host = os.getenv("REDIS_HOST", "127.0.0.1")
        port = int(os.getenv("REDIS_PORT", "6379"))
        db   = int(os.getenv("REDIS_DB",   "0"))
        password = os.getenv("REDIS_PASSWORD", None)

        self._r = Redis(host=host, port=port, db=db, password=password, decode_responses=False)

        # Canal propio de escucha
        self._my_channel = self._names.get(self._node)
        if not self._my_channel:
            raise RuntimeError(f"No hay canal para nodo {self._node} en {names_path}")

    def _load_names(self, path: str) -> dict[str, str]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("type") == "names"
        return data["config"]

    def me(self) -> str:
        return self._node

    async def run(self) -> AsyncIterator[Dict[str, Any]]:
        pubsub = self._r.pubsub()
        await pubsub.subscribe(self._my_channel)

        async for msg in pubsub.listen():
            # Estructura: {'type':'message'|'subscribe'..., 'channel': b'router:A', 'data': b'...'}
            if msg.get("type") != "message":
                continue
            data = msg.get("data")
            if isinstance(data, (bytes, bytearray)):
                try:
                    raw = json.loads(data.decode("utf-8"))
                except Exception:
                    continue
            elif isinstance(data, str):
                try:
                    raw = json.loads(data)
                except Exception:
                    continue
            else:
                continue

            # Normaliza campos minimos
            raw.setdefault("from", raw.get("from") or self._node)
            raw.setdefault("origin", raw["from"])
            raw.setdefault("via", raw["from"])

            yield raw

    async def send(self, to: str, message: Dict[str, Any]) -> None:
        channel = self._names.get(to)
        if not channel:
            return
        try:
            wire = json.dumps(message, separators=(",", ":")).encode("utf-8")
            await self._r.publish(channel, wire)
        except Exception:
            # tolerante a fallos transitorios
            return
