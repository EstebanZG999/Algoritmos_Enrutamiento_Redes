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

        self.adj_observed: Dict[str, Dict[str, float]] = {}  # bordes aprendidos por tráfico
        self._dist: Dict[str, float] = {}

    # -------------------------------
    # Interfaz estilo RoutingAlgorithm
    # -------------------------------
    def on_init(self, me: str, neighbors) -> None:
        """
        Nodos nacen con tabla vacía y registran solo la "lista/costos" de vecinos conocidos por config, 
        pero NO poblan la LSDB hasta recibir HELLO de ellos.
        """
        self.me = me
        if isinstance(neighbors, dict):
            self._neighbors_costs = {n: float(w) for n, w in neighbors.items()}
            self._neighbors_list = list(neighbors.keys())
        else:
            self._neighbors_list = list(neighbors)
            self._neighbors_costs = {n: 1.0 for n in self._neighbors_list}

        # Arrancamos VACÍOS (sin entradas en LSDB)
        self.lsdb = {}
        self._prev, self._next = {}, {}
        # Mantén el motor de flooding
        self._flood = FloodingAlgo(self.me, self._neighbors_list)

        # Tabla vacía al inicio
        self._graph = Graph(undirected=True)
        self._dist = {}
        self._seen_seq = {}

        # Log “tabla vacía”
        print(f"[{self.me}] init: tabla vacía; vecinos conocidos={self._neighbors_list}")

    def mark_neighbor_active(self, neighbor: str, metric: float = 1.0) -> bool:
        """
        Marca/actualiza un vecino como ACTIVO dentro de mi LSDB (entrada propia).
        Devuelve True si la LSDB cambió.
        """
        if self.me not in self.lsdb:
            self.lsdb[self.me] = {}
        old = self.lsdb[self.me].get(neighbor)
        new = float(metric)
        if old is None or old != new:
            self.lsdb[self.me][neighbor] = new
            return True
        return False

    def is_neighbor_known(self, neighbor: str) -> bool:
        """Devuelve True si el vecino está en la lista conocida por config."""
        return neighbor in self._neighbors_costs or neighbor in self._neighbors_list


    def on_hello(self, neighbor: str, metric: float = 1.0) -> None:
        self._neighbors_costs[neighbor] = float(metric)
        # Activa solo este vecino en mi LSDB
        changed = self.mark_neighbor_active(neighbor, metric)
        if changed:
            self._bump_seq(self.me)
            self.recompute()

    def on_info(self, from_node: str, payload: Dict[str, Any]) -> None:
        if not payload:
            return

        # 1) Desenrollar si viene como {"lsp": {...}}
        if "lsp" in payload and isinstance(payload["lsp"], dict):
            payload = payload["lsp"]

        # 2) Formato A: {"lsdb": {"A": {...}, "B": {...}}}
        if "lsdb" in payload and isinstance(payload["lsdb"], dict):
            changed = False
            for node, neighs in payload["lsdb"].items():
                if not isinstance(neighs, dict):
                    continue
                norm = {n: float(w) for n, w in neighs.items()}
                if node not in self.lsdb or self.lsdb[node] != norm:
                    self.lsdb[node] = norm
                    changed = True
            if changed:
                self.recompute()
            return

        # 3) Formato B: {"self": "A", "neighbors": {...}, "seq": 12}
        lsp_src = payload.get("self") or from_node
        nbrs = payload.get("neighbors")
        seq = int(payload.get("seq", 0))
        if not isinstance(nbrs, dict):
            return

        last = self._seen_seq.get(lsp_src, -1)
        if seq <= last:
            return
        self._seen_seq[lsp_src] = seq

        norm = {n: float(w) for n, w in nbrs.items()}
        if lsp_src not in self.lsdb or self.lsdb[lsp_src] != norm:
            self.lsdb[lsp_src] = norm
            self.recompute()

    def recompute(self) -> None:
        self._graph = self._build_graph_from_sources()
        dist, prev = dijkstra(self._graph, self.me)
        self._dist = dist
        self._prev = {str(k): (None if v is None else str(v)) for k, v in prev.items()}

        nh = {}
        for dest in self._prev.keys():
            if dest == self.me: nh[dest] = None; continue
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
    
    def on_edge_observed(self, u: str, v: str, w: float) -> bool:
        print(f"[{self.me}] on_edge_observed(u={u}, v={v}, w_in={w})", flush=True)
        w = float(w)
        changed = False
        d = self.adj_observed.setdefault(u, {})
        if d.get(v, float("inf")) > w:
            d[v] = w; changed = True
        d2 = self.adj_observed.setdefault(v, {})
        if d2.get(u, float("inf")) > w:
            d2[u] = w; changed = True
        if changed:
            print(f"[{self.me}] learned edge {u}<->{v} w={w}")
        return changed
    
    def _build_graph_from_sources(self) -> Graph:
        g = Graph(undirected=True)
        # 1) mis enlaces directos vivos (HELLO aceptados)
        if self.me in self.lsdb:
            for v, w in self.lsdb[self.me].items():
                g.add_edge(self.me, v, float(w))
        # 2) adyacencias observadas
        for u, nbrs in self.adj_observed.items():
            for v, w in nbrs.items():
                g.add_edge(u, v, float(w))
        # 3) LSPs de otros (si on_info pobló lsdb)
        for u, nbrs in self.lsdb.items():
            if u == self.me: continue
            for v, w in nbrs.items():
                g.add_edge(u, v, float(w))
        return g
    
    def _bump_seq(self, node: str) -> int:
        cur = int(self._seen_seq.get(node, 0)) + 1
        self._seen_seq[node] = cur
        return cur
