# Distance Vector (minimo)
from typing import Dict, Any, Optional

class DistanceVector:
    name = "dvr"

    def __init__(self):
        self.me: str = ""
        self.neighbors: list[str] = []
        self.dv: Dict[str, Dict[str, Any]] = {}      # destino
        self.recv: Dict[str, Dict[str, float]] = {}  # vecino
        self.cost: Dict[str, float] = {}             # costo directo a vecinos

    def on_init(self, me: str, neighbors: list[str]) -> None:
        self.me = me
        self.neighbors = neighbors[:]
        self.cost = {n: 1.0 for n in neighbors}
        self.dv[self.me] = {"cost": 0.0, "next": None}

    def on_hello(self, neighbor: str, metric: float = 1.0) -> None:
        if neighbor not in self.cost:
            self.cost[neighbor] = metric
            if neighbor not in self.neighbors:
                self.neighbors.append(neighbor)

    def on_info(self, from_node: str, payload: Dict[str, Any]) -> None:
        vector = payload.get("vector", {})
        self.recv[from_node] = {d: float(c) for d, c in vector.items() if float(c) >= 0}

    def recompute(self) -> None:
        changed = False
        all_dests = set(self.dv.keys()) | {self.me}
        for v in self.recv.values():
            all_dests |= set(v.keys())

        for dest in all_dests:
            if dest == self.me:
                self.dv[self.me] = {"cost": 0.0, "next": None}
                continue
            best_cost = self.dv.get(dest, {}).get("cost", float("inf"))
            best_next = self.dv.get(dest, {}).get("next", None)

            for nbr in self.neighbors:
                c_me_nbr = self.cost.get(nbr, float("inf"))
                c_nbr_dest = self.recv.get(nbr, {}).get(dest, float("inf"))
                cand = c_me_nbr + c_nbr_dest
                if cand < best_cost:
                    best_cost, best_next = cand, nbr

            if best_cost != self.dv.get(dest, {}).get("cost", float("inf")) or best_next != self.dv.get(dest, {}).get("next", None):
                self.dv[dest] = {"cost": best_cost, "next": best_next}
                changed = True

    def next_hop(self, dest: str) -> Optional[str]:
        e = self.dv.get(dest)
        return None if not e else e.get("next")

    def build_info(self) -> Dict[str, Any]:
        return {"vector": {d: float(v["cost"]) for d, v in self.dv.items() if v["cost"] < float("inf")}}
