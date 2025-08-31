# src/routerlab/core/forwarding.py
# Logica de forwarding (demo con Flooding)
import asyncio, time
from typing import Dict, Any, Callable, Set, Deque, Optional
from collections import deque
from routerlab.core.messages import Message

class Forwarder:
    def __init__(self,
                 send_func: Callable[[str, Dict[str, Any]], "asyncio.Future"],
                 neighbors: list[str],
                 me: str,
                 seen_ttl: float = 15.0,
                 route_next_hop: Optional[Callable[[str], Optional[str]]] = None,
                 route_event_queue: Optional[asyncio.Queue] = None,
        ):
        self._send = send_func
        self._neighbors = neighbors
        self._me = me
        self._seen: Set[str] = set()
        self._order: Deque[tuple[str,float]] = deque()
        self._seen_ttl = seen_ttl
        self._route_next_hop = route_next_hop
        self._rq = route_event_queue

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

        # TTL
        if msg.ttl <= 0:
            return

        # Entregar eventos de control a la capa de routing
        if msg.type in ("hello", "info") and self._rq is not None:
            await self._rq.put({"type": msg.type, "from": msg.from_, "payload": msg.payload})

        # Entrega local de DATA
        if msg.type == "message":
            if msg.to == self._me:
                # Unicast: entrego y NO reenvoo
                print(f"[{self._me}] RX from {msg.origin}: {msg.payload}")
                return
            if msg.to == "*":
                # Broadcast: entrego localmente PERO continuo flooding
                print(f"[{self._me}] RX from {msg.origin}: {msg.payload}")

        # Encaminamiento segun proto
        if msg.proto == "flooding":
            # Flooding: reenviar a todos los vecinos menos el emisor
            nxt = msg.dec()
            nxt.from_ = self._me
            nxt.via = self._me
            wire = nxt.as_wire()

            prev_hop = getattr(msg, "via", None) or msg.from_
            tasks = []
            for nbr in self._neighbors:
                if nbr == prev_hop:
                    continue
                tasks.append(self._send(nbr, wire))
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
            return

        if msg.proto == "dvr":
            # DVR: usar next_hop calculado por el algoritmo
            if msg.to != self._me and self._route_next_hop is not None:
                nh = self._route_next_hop(msg.to)
                if nh:
                    await self._send(nh, msg.dec().as_wire())
            return

        # Otros protos (LSR, etc.)