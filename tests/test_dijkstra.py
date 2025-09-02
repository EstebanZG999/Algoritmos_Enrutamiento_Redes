# tests/test_dijkstra.py
# Pruebas unitarias para el algoritmo de Dijkstra en routerlab
# Ejecuta:
#   PYTHONPATH=src pytest -q tests/test_dijkstra.py
# o con tu Makefile:
#   make test TEST=tests/test_dijkstra.py

import json
import pytest

from src.routerlab.algorithms.dijkstra import (
    Graph,
    routing_from,
    reconstruct_path,
    Dijkstra,
    load_graph_from_topo,
)

# ---------- Casos base: grafo sin pesos (costo 1 por arista) ----------

def test_unweighted_line_topology_routing():
    """
    Topología en línea: A - B - C
    Debe forzar que A -> C salga por B (next-hop = B).
    """
    g = Graph(undirected=True)
    g.add_edge("A", "B", 1)
    g.add_edge("B", "C", 1)

    res = routing_from(g, "A")
    dist = res["dist"]
    nh   = res["next_hop"]

    assert dist["A"] == 0
    assert dist["B"] == 1
    assert dist["C"] == 2
    assert nh["B"] == "B"
    assert nh["C"] == "B"   # primer salto desde A hacia C debe ser B

    path = reconstruct_path(res["prev"], "A", "C")
    assert path == ["A", "B", "C"]


def test_unreachable_destination_returns_none_next_hop():
    """
    Si un destino no está en el grafo (o es inalcanzable),
    next-hop debe ser None (o no existir).
    """
    g = Graph(undirected=True)
    g.add_edge("A", "B", 1)
    # C no conectado / no presente
    res = routing_from(g, "A")
    nh = res["next_hop"]

    # Si C no existe en prev, next_hop.get('C') será None (comportamiento esperado).
    assert nh.get("C") is None


# ---------- Pesos: preferencia por el camino de menor costo ----------

def test_weighted_prefers_lower_cost_path():
    """
    Grafo:
      A -1- B -100- C
      A -1- D -1--- C
    Debe preferir A -> D -> C (costo 2) sobre A -> B -> C (costo 101).
    """
    g = Graph(undirected=True)
    g.add_edge("A", "B", 1)
    g.add_edge("B", "C", 100)
    g.add_edge("A", "D", 1)
    g.add_edge("D", "C", 1)

    res = routing_from(g, "A")
    dist = res["dist"]
    nh   = res["next_hop"]

    assert dist["C"] == 2
    assert nh["C"] == "D"   # primer salto hacia C debe ser D
    assert reconstruct_path(res["prev"], "A", "C") == ["A", "D", "C"]


# ---------- Carga desde topo-*.txt y clase Dijkstra ----------

def test_load_graph_from_topo_and_class_on_init(tmp_path):
    """
    Usa un archivo topo JSON y valida que Dijkstra (clase) compute next-hops.
    Topología en línea: A - B - C
    """
    topo = {
        "type": "topo",
        "config": {
            "A": ["B"],
            "B": ["A", "C"],
            "C": ["B"]
        }
    }
    topo_file = tmp_path / "topo-line.json"
    topo_file.write_text(json.dumps(topo), encoding="utf-8")

    # Carga vía helper
    g = load_graph_from_topo(topo_file)
    res = routing_from(g, "A")
    assert res["next_hop"]["C"] == "B"

    # Carga vía clase Dijkstra (on_init)
    alg = Dijkstra(topo_path=str(topo_file))
    alg.on_init(me="A", neighbors=["B"])  # neighbors no afectan el cálculo estático
    assert alg.next_hop("C") == "B"


@pytest.mark.parametrize(
    "cfg,expected_first_hop",
    [
        # Triángulo: A conectado con B y C; next-hop hacia C puede ser C directamente
        ({"A": ["B", "C"], "B": ["A", "C"], "C": ["A", "B"]}, "C"),
        # En línea: fuerza pasar por B
        ({"A": ["B"], "B": ["A", "C"], "C": ["B"]}, "B"),
    ],
)
def test_class_next_hop_various_topologies(tmp_path, cfg, expected_first_hop):
    topo = {"type": "topo", "config": cfg}
    topo_file = tmp_path / "topo.json"
    topo_file.write_text(json.dumps(topo), encoding="utf-8")

    alg = Dijkstra(topo_path=str(topo_file))
    alg.on_init(me="A", neighbors=list(cfg.get("A", [])))
    assert alg.next_hop("C") == expected_first_hop
