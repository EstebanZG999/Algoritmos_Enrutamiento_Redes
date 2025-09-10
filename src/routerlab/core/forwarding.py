# src/routerlab/core/forwarding.py
# Logica de forwarding (demo con Flooding)
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
        Manejo robusto de paquetes:
        - No crashea si llegan tipos desconocidos (ej. 'lsp' de otros equipos).
        - En 'lsp' los reenvía a la cola de routing si existe; en flooding los ignora.
        - Mantiene dedup por id y TTL.
        """
        # 1) Si es un LSP, NO intentes validar con Message (evita crash por Literal)
        pkt_type = raw.get("type")
        if pkt_type == "lsp":
            # Si tienes cola de eventos de routing, pásalo; si no, lo descartas.
            if self._rq is not None:
                await self._rq.put({"type": "lsp", "from": raw.get("from"), "payload": raw.get("payload", {})})
            return

        # 2) Validación normal para los demás tipos
        try:
            msg = Message(**raw)
        except ValidationError:
            # Paquete inválido o de tipo desconocido → lo descartamos con log suave
            print(f"[{self._me}] drop unknown/invalid packet: {raw.get('type')}")
            return

        # 3) Normalización mínima
        if not msg.origin:
            msg.origin = msg.from_

        # 4) Dedup anti-loop
        if msg.id in self._seen:
            return
        self._seen.add(msg.id)
        self._order.append((msg.id, time.time()))
        self._gc_seen()

        # 5) TTL
        if msg.ttl <= 0:
            return

        # 6) Entregar eventos de control a routing (hello/info)
        if msg.type in ("hello", "info") and self._rq is not None:
            await self._rq.put({"type": msg.type, "from": msg.from_, "payload": msg.payload})

        # 7) Entrega local de DATA
        if msg.type == "message":
            if msg.to == self._me:
                print(f"[{self._me}] RX from {msg.origin}: {msg.payload}")
                return
            if msg.to == "*":
                # Broadcast: entrego localmente y sigo flooding
                print(f"[{self._me}] RX from {msg.origin}: {msg.payload}")

        # 7.1) Broadcast universal: si es DATA y to="*", floodea SIEMPRE
        if msg.type == "message" and msg.to == "*":
            # Aprendizaje de arista (Persona 2)
            if self._rq is not None:
                prev_hop = getattr(msg, "via", None) or msg.from_
                if prev_hop and prev_hop != self._me:
                    await self._rq.put({"type": "edge", "from": prev_hop,
                                        "payload": {"to": self._me, "w": 1.0}})

            # Flooding (idéntico a la rama flooding)
            nxt = msg.dec()
            if nxt.ttl <= 0:
                return
            # incrementa hops en el payload
            payload = nxt.payload if isinstance(nxt.payload, dict) else {}
            payload["hops"] = int(payload.get("hops", 0)) + 1
            nxt.payload = payload

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

        # 8) Encaminamiento según proto
        if msg.proto == "flooding":
            # Reenvía a todos los vecinos excepto el salto previo
            nxt = msg.dec()            # TTL-1
            if nxt.ttl <= 0:
                return
            nxt.from_ = self._me
            nxt.via = self._me
            wire = nxt.as_wire()

            # Determinar hop anterior (prefiere 'via', cae a 'from')
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
            # Usa next-hop calculado por el algoritmo
            if msg.to != self._me and self._route_next_hop is not None:
                nh = self._route_next_hop(msg.to)
                if nh:
                    nxt = msg.dec()
                    if nxt.ttl > 0:
                        await self._send(nh, nxt.as_wire())
            return

        # Otros protos → por ahora, descartar en silencio
        return