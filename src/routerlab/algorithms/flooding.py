# src/routerlab/algorithms/flooding.py
# Flooding algorithm (TTL + dedup + anti-echo)

import time, uuid
from typing import Dict, Any, List, Set, Tuple
from collections import deque

class FloodingAlgo:
    """
    Algoritmo de Flooding con:
      - TTL decreciente
      - Deduplicación por msg.id con garbage-collector
      - Anti-eco (no reenvía al vecino por el que vino el paquete)
    Este módulo es independiente del driver/forwarder.
    """

    def __init__(self, me: str, neighbors: List[str], seen_ttl: float = 15.0):
        self.me = me
        self.neighbors = list(neighbors)
        self.seen_ttl = float(seen_ttl)
        self._seen: Set[str] = set()
        self._order: deque[Tuple[str,float]] = deque()

    def _gc_seen(self):
        now = time.time()
        while self._order and (now - self._order[0][1]) > self.seen_ttl:
            mid, _ = self._order.popleft()
            self._seen.discard(mid)

    def should_forward(self, msg_id: str, ttl: int) -> bool:
        """Devuelve True si el mensaje es nuevo y TTL>0, False si debe descartarse."""
        self._gc_seen()
        if ttl <= 0 or msg_id in self._seen:
            return False
        self._seen.add(msg_id)
        self._order.append((msg_id, time.time()))
        return True

    def build_data(self, to: str, payload: Dict[str, Any], msg_id: str = None, ttl: int = 8) -> Dict[str, Any]:
        """Construye un paquete {type,message,...} listo para enviar."""
        if not msg_id:
            msg_id = str(uuid.uuid4())
        return {
            "type": "message",
            "from": self.me,
            "to": to,
            "id": msg_id,
            "ttl": ttl,
            "payload": payload,
        }

    def forward(self, msg: Dict[str, Any], prev_hop: str) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Decide a quién reenviar un mensaje.
        Devuelve lista de (vecino, paquete).
        """
        if not self.should_forward(msg["id"], msg.get("ttl", 0)):
            return []

        new_msg = dict(msg)
        new_msg["ttl"] = new_msg.get("ttl", 0) - 1
        new_msg["from"] = self.me

        out = []
        for nbr in self.neighbors:
            if nbr == prev_hop:
                continue
            out.append((nbr, new_msg))
        return out
