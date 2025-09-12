# src/routerlab/core/forwarding.py
import asyncio, time
from typing import Dict, Any, Callable, Set, Deque, Optional
from collections import deque
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
        Manejo de paquetes en formato simple:
        { "type": "hello"|"message", "from": nodo, "to": nodo, "hops": peso }
        - hello: se pasa a la cola de routing
        - message: se pasa a la cola y se floodea a los demás vecinos
        """
        pkt_type = raw.get("type")

        # Validación mínima
        if "from" not in raw or "to" not in raw or "type" not in raw:
            print(f"[{self._me}] drop invalid packet: {raw}")
            return

        # Deduplicación
        msg_id = f"{raw['from']}->{raw['to']}:{raw['type']}:{raw.get('hops')}"
        if msg_id in self._seen:
            return
        self._seen.add(msg_id)
        self._order.append((msg_id, time.time()))
        self._gc_seen()

        if pkt_type == "hello":
            # Pasar HELLO a la cola de routing
            if self._rq is not None:
                await self._rq.put({
                    "type": "hello",
                    "from": raw["from"],
                    "to": raw["to"],
                    "hops": raw.get("hops", 1.0)
                })
            return

        elif pkt_type == "message":
            # Pasar MESSAGE a la cola de routing
            if self._rq is not None:
                await self._rq.put({
                    "type": "message",
                    "from": raw["from"],
                    "to": raw["to"],
                    "hops": raw.get("hops", 1.0)
                })

            # Flooding → reenvío a todos menos al que lo envió
            prev_hop = raw["from"]
            for nbr in self._neighbors:
                if nbr == prev_hop:
                    continue

                # Clonar mensaje y actualizar "from"
                fwd = dict(raw)
                fwd["from"] = self._me
                print(f"[FWD][{self._me}] reenviando message {fwd} a {nbr}")
                await self._send(nbr, fwd)
            return

        else:
            print(f"[{self._me}] drop unknown packet type: {pkt_type}")
            return
