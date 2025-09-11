# Flooding algorithm (dedup + anti-echo simple)
import time
from typing import Dict, Any, Tuple, Set, Deque, List
from collections import deque

class FloodingAlgo:
    """
    Algoritmo de Flooding simplificado:
      - Deduplicación por (from,to,hops)
      - Anti-eco: excluye al vecino del que vino
      - Sin TTL ni payload, siguiendo el nuevo formato plano
    """

    def __init__(self, me: str, neighbors: List[str], seen_ttl: float = 15.0):
        self.me = me
        self.neighbors = list(neighbors)
        self.seen_ttl = float(seen_ttl)
        self._seen: Set[str] = set()
        self._order: Deque[Tuple[str, float]] = deque()

    # housekeeping
    def _gc_seen(self) -> None:
        now = time.time()
        while self._order and (now - self._order[0][1]) > self.seen_ttl:
            mid, _ = self._order.popleft()
            self._seen.discard(mid)

    def _mark_seen(self, msg_id: str) -> bool:
        """Devuelve False si ya lo vimos; True si lo marca por primera vez."""
        self._gc_seen()
        if msg_id in self._seen:
            return False
        self._seen.add(msg_id)
        self._order.append((msg_id, time.time()))
        return True

    # API principal
    def handle(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        """
        Procesa un mensaje y devuelve una decisión:
        {
          "deliver": bool,                # ¿entregar localmente?
          "outgoing": List[str],          # vecinos a los que reenviar
          "wire": Dict[str, Any] | None,  # mensaje clonado (from = me)
          "reason": str                   # para logs/tests
        }
        """
        # Validación mínima
        if "from" not in msg or "to" not in msg or "type" not in msg:
            return {"deliver": False, "outgoing": [], "wire": None, "reason": "malformed"}

        # Dedup por (from,to,type,hops)
        msg_id = f"{msg['from']}->{msg['to']}:{msg['type']}:{msg.get('hops')}"
        if not self._mark_seen(msg_id):
            return {"deliver": False, "outgoing": [], "wire": None, "reason": "duplicate"}

        # Entrega local: si el destino es este nodo o broadcast "*"
        deliver = (msg.get("to") == self.me) or (msg.get("to") == "*")

        # Preparar copia para reenvío (cambiar el campo "from" a este nodo)
        nxt = dict(msg)
        nxt["from"] = self.me

        # Anti-eco: excluir el vecino por el que entró
        prev_hop = msg.get("from")

        outgoing: List[str] = []
        for n in self.neighbors:
            if n == prev_hop:
                continue
            outgoing.append(n)

        return {
            "deliver": deliver,
            "outgoing": outgoing,
            "wire": nxt if outgoing else None,
            "reason": "ok",
        }
