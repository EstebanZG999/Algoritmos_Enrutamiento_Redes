# Logica de forwarding (demo con Flooding)
import asyncio
from typing import Dict, Any, Callable, Set
from routerlab.core.messages import Message

class Forwarder:
    def __init__(self, send_func: Callable[[str, Dict[str, Any]], "asyncio.Future"], neighbors: list[str], me: str):
        self._send = send_func
        self._neighbors = neighbors
        self._me = me
        self._seen: Set[str] = set()  # deduplicacion por id

    async def handle(self, raw: Dict[str, Any]):
        # Validacion estricta del mensaje entrante
        try:
            msg = Message(**raw)
        except Exception:
            return

        # Dedupe + TTL
        if msg.id in self._seen:
            return
        self._seen.add(msg.id)
        if msg.ttl == 0:
            return

        # Si es DATA y yo soy el destino, imprimir payload
        if msg.type == "message" and msg.to == self._me:
            print(f"[{self._me}] RX from {msg.from_}: {msg.payload}")
            return

        # Flooding “puro”, reenviar a todos los vecinos menos el emisor
        if msg.proto == "flooding":
            nxt = msg.dec().as_wire()
            tasks = []
            for nbr in self._neighbors:
                if nbr == msg.from_:
                    continue
                tasks.append(self._send(nbr, nxt))
            if tasks:
                await asyncio.gather(*tasks)
