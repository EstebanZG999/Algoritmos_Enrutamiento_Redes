# Link State Routing (LSR) con Flooding + Dijkstra (compat dict/list, LSP dual-format, seq dedupe)
from typing import Dict, Any, Optional
from routerlab.algorithms.dijkstra import Graph, dijkstra, _first_hop
from routerlab.algorithms.flooding import FloodingAlgo
import uuid

class LinkState:
    name = "lsr"

    def __init__(self):
        self.me: str = ""
        # Vecinos para el forwarder (lista de ids)
        self._neighbors_list: list[str] = []
        # Costos directos (diccionario)
        self._neighbors_costs: Dict[str, float] = {}
        # Base de estado de enlaces: nodo -> {vecino: costo}
        self.lsdb: Dict[str, Dict[str, float]] = {}
        # Grafo + rutas
        self._graph: Graph = Graph(undirected=True)
        self._prev: Dict[str, Optional[str]] = {}
        self._next: Dict[str, Optional[str]] = {}
        # Seq visto por origen (para dedupe)
        self._seen_seq: Dict[str, int] = {}
        # Motor de flooding interno
        self._flood: Optional[FloodingAlgo] = None

    # -------------------------------
    # Interfaz estilo RoutingAlgorithm
    # -------------------------------
    def on_init(self, me: str, neighbors) -> None:
        """
        neighbors puede ser:
          - list[str]                 → costos = 1.0
          - dict[str, float|int]      → costos dados
        """
        self.me = me
        if isinstance(neighbors, dict):
            self._neighbors_costs = {n: float(w) for n, w in neighbors.items()}
            self._neighbors_list = list(neighbors.keys())
        else:
            self._neighbors_list = list(neighbors)
            self._neighbors_costs = {n: 1.0 for n in self._neighbors_list}

        # Inicializar LSDB con mis enlaces directos
        self.lsdb = {self.me: self._neighbors_costs.copy()}

        # Inicializar flooding (requiere lista)
        self._flood = FloodingAlgo(self.me, self._neighbors_list)

        # Calcular tabla inicial
        self.recompute()

    def on_hello(self, neighbor: str, metric: float = 1.0) -> None:
        self._neighbors_costs[neighbor] = float(metric)
        self.lsdb[self.me] = self._neighbors_costs.copy()
        # Puedes incrementar un seq propio para anunciar cambios
        self._bump_seq(self.me)
        self.recompute()

    def on_info(self, from_node: str, payload: Dict[str, Any]) -> None:
        """
        Acepta dos formatos de LSP:
        A) Propio del repo:
           payload = {"lsdb": {"A": {"B": 1.0, "C": 2.0}}}
        B) Estándar típico:
           payload = {"self": "A", "neighbors": {"B": 1.0, "C": 2.0}, "seq": 12}
        """
        if not payload:
            return

        # --- Formato A (lsdb incrmental) ---
        if "lsdb" in payload and isinstance(payload["lsdb"], dict):
            changed = False
            for node, neighs in payload["lsdb"].items():
                if not isinstance(neighs, dict):
                    continue
                # Sin seq aquí; asumimos actualización válida
                norm = {n: float(w) for n, w in neighs.items()}
                if node not in self.lsdb or self.lsdb[node] != norm:
                    self.lsdb[node] = norm
                    changed = True
            if changed:
                self.recompute()
            return

        # --- Formato B (self/neighbors/seq) ---
        lsp_src = payload.get("self") or from_node
        nbrs = payload.get("neighbors")
        seq = int(payload.get("seq", 0))
        if not isinstance(nbrs, dict):
            return

        # Dedupe por seq
        last = self._seen_seq.get(lsp_src, -1)
        if seq <= last:
            return
        self._seen_seq[lsp_src] = seq

        norm = {n: float(w) for n, w in nbrs.items()}
        if lsp_src not in self.lsdb or self.lsdb[lsp_src] != norm:
            self.lsdb[lsp_src] = norm
            self.recompute()

    def recompute(self) -> None:
        # Construir grafo desde LSDB
        self._graph = Graph(undirected=True)
        for u, neighs in self.lsdb.items():
            for v, w in neighs.items():
                self._graph.add_edge(u, v, float(w))

        # Ejecutar Dijkstra
        dist, prev = dijkstra(self._graph, self.me)
        # Guardamos prev y calculamos next-hop por destino
        self._prev = {str(k): (None if v is None else str(v)) for k, v in prev.items()}
        nh: Dict[str, Optional[str]] = {}
        for dest in self._prev.keys():
            if dest == self.me:
                nh[dest] = None
                continue
            hop = _first_hop(self._prev, self.me, dest)
            nh[dest] = hop if hop is None else str(hop)
        self._next = nh

    def next_hop(self, dest: str) -> Optional[str]:
        return self._next.get(dest)

    def build_info(self) -> Dict[str, Any]:
        """
        Construye LSP propio en formato B (self/neighbors/seq) para interoperar.
        Los equipos que usen formato A podrán integrarlo vía on_info (ramal B).
        """
        return {
            "self": self.me,
            "neighbors": self._neighbors_costs.copy(),
            "seq": self._bump_seq(self.me),
        }

    # -------------------------------
    # Integración con Flooding
    # -------------------------------
    def flood_lsa(self) -> Dict[str, Any]:
        """
        Construye un paquete de flooding con nuestro LSP (broadcast '*').
        """
        if not self._flood:
            raise RuntimeError("Flooding no inicializado (llama a on_init primero).")
        lsp = self.build_info()                 # tu LSP en formato {"self","neighbors","seq"} ó el que uses
        msg_id = str(uuid.uuid4())
        # PUBLICAR EL LSP DENTRO DEL PAYLOAD COMO {"lsp": ...}
        return self._flood.build_data("*", {"lsp": lsp}, msg_id, ttl=8)
