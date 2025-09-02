# Algoritmo de Dijkstra (integración routerlab)
# Descripción:
# - Implementación modular de Dijkstra con:
#   1) clases y funciones de grafo
#   2) dijkstra(), reconstrucción de rutas y next-hop
#   3) clase Dijkstra con interfaz estilo RoutingAlgorithm (on_init/next_hop/etc.)
# - Carga la topología desde configs/topo-*.txt (JSON con {"type":"topo","config":{...}})
# - Útil como módulo local (standalone) y como bloque dentro de LSR en el futuro.

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Hashable, Iterable, List, Tuple, Optional
from pathlib import Path
import heapq, json

# -----------------------
#   Tipos y estructura
# -----------------------

Node = Hashable

@dataclass(frozen=True)
class Edge:
    u: Node
    v: Node
    w: float = 1.0

class Graph:
    """
    Grafo sencillo con lista de adyacencia.
    Por defecto se asume no dirigido (undirected=True).
    """
    def __init__(self, undirected: bool = True) -> None:
        self.adj: Dict[Node, List[Tuple[Node, float]]] = {}
        self.undirected = undirected

    def add_edge(self, u: Node, v: Node, w: float = 1.0) -> None:
        self.adj.setdefault(u, []).append((v, w))
        if self.undirected:
            self.adj.setdefault(v, []).append((u, w))
        else:
            self.adj.setdefault(v, [])  # asegura presencia del nodo

    def add_edges_from(self, edges: Iterable[Edge]) -> None:
        for e in edges:
            self.add_edge(e.u, e.v, e.w)

    def neighbors(self, u: Node) -> List[Tuple[Node, float]]:
        return self.adj.get(u, [])

    def nodes(self) -> List[Node]:
        return list(self.adj.keys())

# -----------------------
#   Core de Dijkstra
# -----------------------

def dijkstra(graph: Graph, source: Node) -> Tuple[Dict[Node, float], Dict[Node, Optional[Node]]]:
    """
    Ejecuta Dijkstra desde 'source'.
    Retorna:
      - dist: distancia mínima a cada nodo (inf si inalcanzable)
      - prev: predecesor inmediato en la ruta más corta (None si origen o inalcanzable)
    """
    dist: Dict[Node, float] = {u: float('inf') for u in graph.nodes()}
    prev: Dict[Node, Optional[Node]] = {u: None for u in graph.nodes()}

    if source not in dist:
        # Si el origen no está en el grafo, lo añadimos sin vecinos
        dist[source] = 0.0
        prev[source] = None
        graph.adj.setdefault(source, [])

    dist[source] = 0.0
    pq: List[Tuple[float, Node]] = [(0.0, source)]

    while pq:
        du, u = heapq.heappop(pq)
        if du > dist[u]:
            continue
        for v, w in graph.neighbors(u):
            alt = du + w
            if alt < dist[v] or (alt == dist[v] and tie_break(u, prev[v])):
                dist[v] = alt
                prev[v] = u
                heapq.heappush(pq, (alt, v))

    return dist, prev

def tie_break(candidate_prev: Optional[Node], current_prev: Optional[Node]) -> bool:
    """
    Criterio simple de desempate (opcional): prefiere el predecesor lexicográficamente menor
    cuando existen rutas de costo idéntico. Si tus nodos no son comparables, puedes apagar esto.
    """
    if candidate_prev is None:
        return False
    if current_prev is None:
        return True
    try:
        return str(candidate_prev) < str(current_prev)
    except Exception:
        return False

def reconstruct_path(prev: Dict[Node, Optional[Node]], source: Node, target: Node) -> List[Node]:
    """
    Reconstruye la ruta source -> target usando el mapa de predecesores 'prev'.
    Retorna lista vacía si 'target' es inalcanzable.
    """
    path: List[Node] = []
    cur: Optional[Node] = target
    while cur is not None:
        path.append(cur)
        if cur == source:
            break
        cur = prev.get(cur)
    path.reverse()
    if not path or path[0] != source:
        return []  # inalcanzable
    return path

def build_next_hops(prev: Dict[Node, Optional[Node]], source: Node) -> Dict[Node, Optional[Node]]:
    """
    Construye la tabla de next-hop desde 'source' hacia todos los destinos alcanzables.
    Para cada destino d != source:
      - next_hop[d] = primer salto desde source siguiendo 'prev' hasta d
    Si d inalcanzable -> None.
    """
    next_hop: Dict[Node, Optional[Node]] = {}
    for dest in prev.keys():
        if dest == source:
            next_hop[dest] = None
            continue
        hop = _first_hop(prev, source, dest)
        next_hop[dest] = hop
    return next_hop

def _first_hop(prev: Dict[Node, Optional[Node]], source: Node, dest: Node) -> Optional[Node]:
    # Recorre hacia atrás: dest <- ... <- source, y toma el nodo justo después de source
    path = reconstruct_path(prev, source, dest)
    if not path or path[0] != source or len(path) < 2:
        return None
    return path[1]

def routing_from(graph: Graph, source: Node) -> Dict[str, Dict[Node, Optional[Node]]]:
    """
    Función de conveniencia:
      - corre Dijkstra
      - arma next_hops
    Retorna dict con 'dist', 'prev', 'next_hop'.
    """
    dist, prev = dijkstra(graph, source)
    next_hop = build_next_hops(prev, source)
    return {"dist": dist, "prev": prev, "next_hop": next_hop}

# -----------------------
#   Loader de topología
# -----------------------

def load_graph_from_topo(path: str | Path, undirected: bool = True) -> Graph:
    """
    Carga un grafo desde el formato del anexo del laboratorio:
    { "type":"topo", "config": { "A": ["B","C"], "B": ["A"], "C": [] } }

    También acepta pesos por arista usando dict:
    { "type":"topo", "config": { "A": {"B": 3, "C": 5}, "B": {"A": 3}, "C": {} } }
    """
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("type") == "topo", "topo inválido: se espera {'type':'topo','config':{...}}"

    cfg = data.get("config", {})
    g = Graph(undirected=undirected)

    for u, neigh in cfg.items():
        if isinstance(neigh, list):
            for v in neigh:
                g.add_edge(u, v, 1.0)
        elif isinstance(neigh, dict):
            for v, w in neigh.items():
                g.add_edge(u, v, float(w))
        else:
            raise ValueError(f"Vecinos de {u} deben ser list o dict.")
    return g

# -----------------------
#   Clase Dijkstra (API estilo RoutingAlgorithm)
# -----------------------

class Dijkstra:
    """
    Implementación estilo 'RoutingAlgorithm':
      - on_init(me, neighbors): carga topo y calcula next_hop desde 'me'
      - next_hop(dest): devuelve el primer salto hacia 'dest'
      - on_hello/on_info/build_info: no-ops para Dijkstra local (sin intercambio de estado)
    """
    name = "dijkstra"

    def __init__(self, topo_path: Optional[str] = None, undirected: bool = True) -> None:
        self.me: str = ""
        self.neighbors: list[str] = []
        self._topo_path = topo_path
        self._undirected = undirected
        self._graph: Graph = Graph(undirected=self._undirected)
        self._prev: Dict[str, Optional[str]] = {}
        self._next: Dict[str, Optional[str]] = {}

    # ---- Interfaz tipo RoutingAlgorithm ----
    def on_init(self, me: str, neighbors: list[str]) -> None:
        self.me = me
        self.neighbors = neighbors[:]
        # Cargar grafo completo desde topología
        if self._topo_path:
            self._graph = load_graph_from_topo(self._topo_path, undirected=self._undirected)
        else:
            # Grafo mínimo con solo el nodo me (útil para pruebas)
            self._graph = Graph(undirected=self._undirected)
            self._graph.adj.setdefault(self.me, [])
        self.recompute()

    def on_hello(self, neighbor: str, metric: float = 1.0) -> None:
        # Dijkstra local no usa HELLO; ignorar
        return

    def on_info(self, from_node: str, payload: Dict[str, object]) -> None:
        # Dijkstra local no intercambia INFO; ignorar
        return

    def recompute(self) -> None:
        # Ejecuta dijkstra y construye tabla de next-hops
        dist, prev = dijkstra(self._graph, self.me)
        # Guardamos prev como strings (coherencia con el resto del framework)
        self._prev = {str(k): (None if v is None else str(v)) for k, v in prev.items()}
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

    def build_info(self) -> Dict[str, object]:
        # Dijkstra local no publica estado
        return {}