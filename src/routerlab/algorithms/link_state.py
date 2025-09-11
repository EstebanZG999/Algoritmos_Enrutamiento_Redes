# Link State Routing (LSR) con Flooding + Dijkstra (mensajes planos)
from typing import Dict, Any, Optional
from routerlab.algorithms.dijkstra import Graph, dijkstra, _first_hop
from routerlab.algorithms.flooding import FloodingAlgo

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
            self.recompute()

    def on_message(self, from_node: str, to_node: str, hops: float) -> None:
        if from_node not in self.lsdb:
            self.lsdb[from_node] = {}
        old = self.lsdb[from_node].get(to_node)
        if old is None or old != float(hops):
            self.lsdb[from_node][to_node] = float(hops)
            print(f"[{self.me}] Aprendí un nuevo enlace: {from_node} -> {to_node} (hops={hops})")
            self.recompute()

    def recompute(self) -> None:
        self._graph = self._build_graph_from_sources()
        dist, prev = dijkstra(self._graph, self.me)
        self._dist = dist
        self._prev = {str(k): (None if v is None else str(v)) for k, v in prev.items()}

        nh = {}
        for dest in self._prev.keys():
            if dest == self.me:
                nh[dest] = None
                continue
            hop = _first_hop(self._prev, self.me, dest)
            nh[dest] = hop if hop is None else str(hop)
        self._next = nh
        self.print_lsdb()
        self.print_routes()

    def next_hop(self, dest: str) -> Optional[str]:
        return self._next.get(dest)

    # -------------------------------
    # Integración con Flooding
    # -------------------------------
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
        # 3) LSPs de otros (ya poblados en lsdb vía on_message)
        for u, nbrs in self.lsdb.items():
            if u == self.me:
                continue
            for v, w in nbrs.items():
                g.add_edge(u, v, float(w))
        return g

    # -------------------------------
    # Utilidades de Tabla / Inspección
    # -------------------------------
    def lsdb_snapshot(self) -> dict[str, dict[str, float]]:
        """
        LSDB consolidada = enlaces directos vivos (self.lsdb[self.me])
                         + adyacencias observadas (self.adj_observed)
                         + LSPs de otros (self.lsdb[otros]).
        """
        snap: dict[str, dict[str, float]] = {}

        # enlaces directos vivos (hello)
        if self.me in self.lsdb:
            snap[self.me] = {v: float(w) for v, w in self.lsdb[self.me].items()}

        # adyacencias observadas
        for u, nbrs in self.adj_observed.items():
            d = snap.setdefault(u, {})
            for v, w in nbrs.items():
                d[v] = min(float(w), float(d.get(v, float("inf"))))

        # LSPs de otros nodos
        for u, nbrs in self.lsdb.items():
            if u == self.me:
                continue
            d = snap.setdefault(u, {})
            for v, w in nbrs.items():
                d[v] = min(float(w), float(d.get(v, float("inf"))))

        return snap

    def _fmt_cost(self, x):
        try:
            x = float(x)
            return int(x) if x.is_integer() else round(x, 3)
        except Exception:
            return x

    def print_lsdb(self):
        """Imprime la LSDB consolidada (legible)."""
        snap = self.lsdb_snapshot()
        print(f"[{self.me}] LSDB:")
        for u in sorted(snap.keys()):
            parts = [f"{v}:{self._fmt_cost(w)}" for v, w in sorted(snap[u].items())]
            print(f"  {u} -> {{ " + ", ".join(parts) + " }}")

    def print_routes(self):
        """Imprime la tabla de rutas (distancias desde self.me)."""
        print(f"[{self.me}] Tabla de rutas (Dijkstra):")
        print("Ruta      : Costo")
        print("------------------")
        for dst in sorted(self._dist.keys()):
            if dst == self.me:
                continue
            cost = self._dist.get(dst, float("inf"))
            if cost != float("inf"):
                nh = self._next.get(dst)
                print(f"{self.me} -> {dst} : {self._fmt_cost(cost)} (nh={nh})")
