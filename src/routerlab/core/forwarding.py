# src/routerlab/core/forwarding.py
# Logica de forwarding (demo con Flooding)
import asyncio, time
from typing import Dict, Any, Callable, Set, Deque
from collections import deque
from routerlab.core.messages import Message

class Forwarder:
    def __init__(self,
                 send_func: Callable[[str, Dict[str, Any]], "asyncio.Future"],
                 neighbors: list[str],
                 me: str,
                 seen_ttl: float = 15.0):
        self._send = send_func
        self._neighbors = neighbors
        self._me = me
        self._seen: Set[str] = set()
        self._order: Deque[tuple[str,float]] = deque()
        self._seen_ttl = seen_ttl

    def _gc_seen(self):
        now = time.time()
        while self._order and (now - self._order[0][1]) > self._seen_ttl:
            mid, _ = self._order.popleft()
            self._seen.discard(mid)

    async def handle(self, raw: Dict[str, Any]):
        # Validar y normalizar
        msg = Message(**raw)

        # Si no trae origin, setearlo al primer salto
        if not msg.origin:
            msg.origin = msg.from_

        # Dedup por id
        if msg.id in self._seen:
            return
        self._seen.add(msg.id)
        self._order.append((msg.id, time.time()))
        self._gc_seen()

        # Si es DATA y yo soy el destino, imprimir payload
        if msg.type == "message" and (msg.to == self._me or msg.to == "*"):
            print(f"[{self._me}] RX from {msg.origin}: {msg.payload}")

        # TTL
        if msg.ttl <= 0:
            return

        # Flooding “puro”, reenviar a todos los vecinos menos el emisor
        nxt = msg.dec()
        nxt.from_ = self._me
        nxt.via = self._me
        wire = nxt.as_wire()

        tasks = []
        prev_hop = getattr(msg, "via", None) or msg.from_
        for nbr in self._neighbors:
            if nbr == prev_hop:
                continue
            tasks.append(self._send(nbr, wire))
        if tasks:
            await asyncio.gather(*tasks)
