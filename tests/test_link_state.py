# Tests para LinkState
from routerlab.algorithms.link_state import LinkState

def make_topo_A_B_C():
    """
    Topología:
      A -- B -- C
    Costos = 1
    """
    topo = {
        "A": {"B": 1.0},
        "B": {"A": 1.0, "C": 1.0},
        "C": {"B": 1.0}
    }
    return topo

def test_init_and_neighbors():
    ls = LinkState()
    ls.on_init("A", ["B"])
    # Debe registrar sus vecinos directos en lsdb
    assert "A" in ls.lsdb
    assert ls.lsdb["A"]["B"] == 1.0

def test_build_info_format():
    ls = LinkState()
    ls.on_init("A", ["B"])
    info = ls.build_info()
    # El formato debe ser {"lsdb": {"A": {...}}}
    assert "lsdb" in info
    assert "A" in info["lsdb"]

def test_on_info_updates_lsdb():
    ls = LinkState()
    ls.on_init("A", ["B"])
    payload = {"lsdb": {"B": {"A": 1.0, "C": 1.0}}}
    ls.on_info("B", payload)
    # LSDB debe incluir la entrada de B
    assert "B" in ls.lsdb
    assert ls.lsdb["B"]["C"] == 1.0

def test_routing_next_hop_line_topo():
    """
    Con topología en línea A-B-C:
    - A debe enviar a B si quiere llegar a C
    - C debe enviar a B si quiere llegar a A
    """
    ls = LinkState()
    ls.on_init("A", ["B"])
    # A recibe LSA de B y C
    topo = make_topo_A_B_C()
    for node, neighs in topo.items():
        if node == "A":
            continue
        ls.on_info(node, {"lsdb": {node: neighs}})
    # Recalcula rutas
    ls.recompute()
    # Tabla de next-hop
    assert ls.next_hop("B") == "B"
    assert ls.next_hop("C") == "B"

def test_unreachable_node():
    ls = LinkState()
    ls.on_init("A", ["B"])
    # No sabe nada de C aún
    assert ls.next_hop("C") is None
