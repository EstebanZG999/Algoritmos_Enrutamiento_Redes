# Flooding algorithm (TTL + dedup + anti-echo)
import time
from typing import Dict, Any, Tuple, Set, Deque, List
from collections import deque

class FloodingAlgo:
    """
    Algoritmo de Flooding con:
      - TTL decreciente
      - Deduplicacion por msg.id con garbage-collector
      - Anti-eco (excluye el vecino por el que llego: prev_hop)
    Este modulo es independiente del driver/forwarder: recibe un mensaje,
    decide si entregarlo localmente y a qué vecinos reenviarlo.
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
        Procesa un mensaje y devuelve una decision:
        {
          "deliver": bool,                # ¿entregar localmente?
          "outgoing": List[str],          # vecinos a los que reenviar
          "wire": Dict[str, Any] | None,  # mensaje clonado con TTL-1, via/from = me
          "reason": str                   # para logs/tests
        }
        """
        # Validacion minima
        if "id" not in msg or "ttl" not in msg or "from" not in msg:
            return {"deliver": False, "outgoing": [], "wire": None, "reason": "malformed"}

        # De-dup por id
        if not self._mark_seen(str(msg["id"])):
            return {"deliver": False, "outgoing": [], "wire": None, "reason": "duplicate"}

        # TTL
        ttl = int(msg.get("ttl", 0))
        if ttl <= 0:
            return {"deliver": False, "outgoing": [], "wire": None, "reason": "ttl_expired"}

        # Entrega local: solo si el destino es este nodo o broadcast "*"
        deliver = (msg.get("to") == self.me) or (msg.get("to") == "*")

        # Preparar copia para reenvio (TTL-1) y marcar from/via = me
        nxt = dict(msg)
        nxt["ttl"] = ttl - 1
        nxt["from"] = self.me
        nxt["via"]  = self.me

        # Anti-eco: excluir el vecino por el que entro
        prev_hop = msg.get("via") or msg.get("from")

        # Lista de salida (si aun hay TTL)
        outgoing: List[str] = []
        if nxt["ttl"] >= 0:
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

    # Utilidad para construir DATA de prueba (no requerida por forwarder)
    def build_data(self, dst: str, payload: Any, msg_id: str, ttl: int = 8, origin: str | None = None) -> Dict[str, Any]:
        return {
            "proto": "flooding",
            "type":  "message",
            "id":    str(msg_id),
            "from":  origin or self.me,
            "origin": origin or self.me,
            "via":    origin or self.me,
            "to":    dst,
            "ttl":   int(ttl),
            "headers": [],
            "payload": payload,
        }
