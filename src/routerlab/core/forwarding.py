# src/routerlab/core/forwarding.py
# Lógica de forwarding con Flooding (solo HELLO y MESSAGE)

import asyncio, time
from typing import Dict, Any, Callable, Set, Deque, Optional
from collections import deque
from routerlab.core.messages import Message
from pydantic import ValidationError

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
        """
        Manejo de paquetes en el laboratorio:
        - Deduplicación con TTL.
        - "hello" → descubrimiento de vecinos.
        - "message" → describe adyacencias (from,to,hops).
        - Se floodean los "message" a todos los vecinos menos al anterior.
        """
        print(f"[{self._me}] RAW in handle: {raw}")  # 👈 debug
        try:
            msg = Message(**raw)
        except ValidationError:
            print(f"[{self._me}] drop unknown/invalid packet: {raw.get('type')}")
            return

        # Normalización de origen
        if not msg.origin:
            msg.origin = msg.from_

        # Deduplicación anti-loop
        if msg.id in self._seen:
            return
        self._seen.add(msg.id)
        self._order.append((msg.id, time.time()))
        self._gc_seen()

        # TTL
        if msg.ttl <= 0:
            return

        # Eventos de control: hello y message pasan a la cola de routing
        if msg.type in ("hello", "message") and self._rq is not None:
            await self._rq.put({
                "type": msg.type,
                "from": msg.from_,
                "to": msg.to,
                "hops": getattr(msg, "hops", None)
            })

        # Entrega local de MESSAGE si soy destino o broadcast
        if msg.type == "message":
            if msg.to == self._me:
                print(f"[{self._me}] RX edge: {msg.from_} -> {msg.to} cost={msg.hops}")
                return
            if msg.to == "*":
                print(f"[{self._me}] RX broadcast from {msg.from_} (hops={msg.hops})")

        # Flooding: reenviar MESSAGE a todos los vecinos menos al hop previo
        if msg.type == "message":
            nxt = msg.dec()
            if nxt.ttl <= 0:
                return
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
                await asyncio.gather(*tasks, return_exceptions=True)
            return

        if msg.proto in ("dvr", "dijkstra", "lsr"):
            if msg.to != self._me and self._route_next_hop is not None:
                nh = self._route_next_hop(msg.to)
                if nh:
                    nxt = msg.dec()
                    if nxt.ttl > 0:
                        nxt.from_ = self._me
                        nxt.via = self._me
                        await self._send(nh, nxt.as_wire())
            return

        # Otros protos → descartar
        return
