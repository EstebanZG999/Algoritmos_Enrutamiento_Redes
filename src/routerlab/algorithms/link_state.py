# Link State Routing (LSR) con Flooding + Dijkstra
from typing import Dict, Any, Optional
from routerlab.algorithms.dijkstra import Graph, dijkstra, _first_hop
from routerlab.algorithms.flooding import FloodingAlgo
import uuid, time

class LinkState:
    name = "lsr"

    def __init__(self):
        self.me: str = ""
        self.neighbors: list[str] = []
        self.lsdb: Dict[str, Dict[str, float]] = {}   # nodo -> {vecino: costo}
        self._graph: Graph = Graph(undirected=True)
        self._prev: Dict[str, Optional[str]] = {}
        self._next: Dict[str, Optional[str]] = {}

        # motor de flooding interno
        self._flood: Optional[FloodingAlgo] = None

    # -------------------------------
    # Interfaz estilo RoutingAlgorithm
    # -------------------------------
    def on_init(self, me: str, neighbors: list[str]) -> None:
        self.me = me
        self.neighbors = neighbors[:]

        # Inicializar LSDB con enlaces directos
        self.lsdb[self.me] = {n: 1.0 for n in neighbors}

        # Inicializar flooding engine
        self._flood = FloodingAlgo(me, neighbors)

        # Calcular tabla inicial
        self.recompute()

    def on_hello(self, neighbor: str, metric: float = 1.0) -> None:
        # Actualizamos enlace directo
        self.lsdb.setdefault(self.me, {})[neighbor] = metric
        self.recompute()

    def on_info(self, from_node: str, payload: Dict[str, Any]) -> None:
        """
        Recibe un LSA (ya entregado tras flooding).
        Formato:
          {"lsdb": {"A": {"B": 1.0, "C": 2.0}}}
        """
        links = payload.get("lsdb", {})
        changed = False
        for node, neighs in links.items():
            if node not in self.lsdb or self.lsdb[node] != neighs:
                self.lsdb[node] = neighs.copy()
                changed = True
        if changed:
            self.recompute()

    def recompute(self) -> None:
        # Construir grafo desde LSDB
        self._graph = Graph(undirected=True)
        for u, neighs in self.lsdb.items():
            for v, w in neighs.items():
                self._graph.add_edge(u, v, w)

        # Ejecutar Dijkstra
        dist, prev = dijkstra(self._graph, self.me)
        self._prev = {str(k): (None if v is None else str(v)) for k, v in prev.items()}

        # Construir tabla de next-hop
        next_hop: Dict[str, Optional[str]] = {}
        for dest in self._prev.keys():
            if dest == self.me:
                next_hop[dest] = None
                continue
            hop = _first_hop(self._prev, self.me, dest)
            next_hop[dest] = hop if hop is None else str(hop)
        self._next = next_hop

    def next_hop(self, dest: str) -> Optional[str]:
        return self._next.get(dest)

    def build_info(self) -> Dict[str, Any]:
        """
        Construye un LSA propio para floodear.
        """
        return {"lsdb": {self.me: self.lsdb.get(self.me, {})}}

    # -------------------------------
    # Integración con Flooding
    # -------------------------------
    def flood_lsa(self) -> Dict[str, Any]:
        """
        Construye un paquete de flooding con nuestro LSA.
        """
        if not self._flood:
            raise RuntimeError("Flooding no inicializado (llama a on_init primero).")
        lsa = self.build_info()
        msg_id = str(uuid.uuid4())
        return self._flood.build_data("*", lsa, msg_id, ttl=8)
