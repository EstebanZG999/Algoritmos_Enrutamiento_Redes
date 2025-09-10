# Link State Routing (LSR) con Flooding + Dijkstra (compat dict/list, seq dedupe)
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
        # Motor de flooding
        self._flood = FloodingAlgo(self.me, self._neighbors_list)

        # Tabla vacía al inicio
        self._graph = Graph(undirected=True)
        self._dist = {}
        self._seen_seq = {}

        # Debug inicial
        print(f"[{self.me}] init: tabla vacía; vecinos conocidos={self._neighbors_list}")
        self.print_lsdb()
        self.print_routing_table()

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
        changed = self.mark_neighbor_active(neighbor, metric)
        if changed:
            self._bump_seq(self.me)
            self.recompute()
            # 🔥 Floodear la nueva arista propia
            self._flood_edge(self.me, neighbor, metric)

    def on_message(self, src: str, to: str, hops: float) -> None:
        """
        Procesa {type:'message', from:src, to:dst, hops:w}.
        Actualiza la LSDB con la adyacencia src<->to si es nueva o cambió.
        """
        if src not in self.lsdb:
            self.lsdb[src] = {}

        old_cost = self.lsdb[src].get(to)
        new_cost = float(hops)

        if old_cost is None or old_cost != new_cost:
            self.lsdb[src][to] = new_cost
            if to not in self.lsdb:
                self.lsdb[to] = {}
            self.lsdb[to][src] = new_cost
            print(f"[{self.me}] LSDB: agregado edge {src}<->{to} cost={new_cost}")
            self.recompute()
            # 🔥 Floodear la arista recién descubierta
            self._flood_edge(src, to, new_cost)
        else:
            # No hay cambio → no recalcular
            pass

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

        # Debug solo si algo cambió
        self.print_lsdb()
        self.print_routing_table()

    def next_hop(self, dest: str) -> Optional[str]:
        return self._next.get(dest)

    # -------------------------------
    # Flooding de nuevas adyacencias
    # -------------------------------
    def _flood_edge(self, src: str, dst: str, cost: float) -> None:
        """Construye y floodea un mensaje de adyacencia nueva."""
        if not self._flood:
            return
        msg_id = str(uuid.uuid4())
        data = {
            "type": "message",
            "proto": "lsr",
            "from": src,
            "to": dst,
            "id": msg_id,
            "ttl": 8,
            "hops": cost,
        }
        # Se envía a todos los vecinos conocidos
        for nbr in self._neighbors_list:
            if nbr != src and nbr != dst:  # evita rebote inmediato
                out_list = self._flood.forward(data, prev_hop=self.me)
                for target, pkt in out_list:
                    # ⚠️ aquí no tenemos self._send, Forwarder se encarga
                    # Basta con que regrese la lista y Forwarder lo use
                    print(f"[{self.me}] flood: reenviando edge {src}<->{dst} a {target}")

    # -------------------------------
    # Debug / Utilidades
    # -------------------------------
    def print_routing_table(self):
        print(f"\n[{self.me}] Tabla de ruteo (next-hop):")
        if not self._next:
            print("  (vacía)")
            return
        for dest, nh in self._next.items():
            if dest == self.me:
                continue
            print(f"  {self.me} -> {dest} via {nh}")

    def _build_graph_from_sources(self) -> Graph:
        g = Graph(undirected=True)
        for u, nbrs in self.lsdb.items():
            for v, w in nbrs.items():
                g.add_edge(u, v, float(w))
        return g

    def print_lsdb(self):
        print(f"\n[{self.me}] LSDB actual:")
        if not self.lsdb:
            print("  (vacía)")
            return
        for u, nbrs in self.lsdb.items():
            for v, w in nbrs.items():
                print(f"  {u} -> {v} : {w}")

    def _bump_seq(self, node: str) -> int:
        cur = int(self._seen_seq.get(node, 0)) + 1
        self._seen_seq[node] = cur
        return cur
