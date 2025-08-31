import math
import pytest

from routerlab.algorithms.distance_vector import DistanceVector


def test_init_sets_self_zero_and_no_routes_yet():
    dv = DistanceVector()
    dv.on_init(me="A", neighbors=["B", "C"])

    # Propio sin costo 0 y sin next hop
    assert dv.dv["A"]["cost"] == 0.0
    assert dv.dv["A"]["next"] is None

    # Todavia no se conocen rutas (hasta recibir INFOs)
    assert dv.next_hop("B") is None
    assert dv.next_hop("C") is None


def test_direct_neighbor_route_after_info():
    dv = DistanceVector()
    dv.on_init(me="A", neighbors=["B"])

    # B anuncia su vector (a si mismo costo 0)
    dv.on_info("B", {"vector": {"B": 0}})
    dv.recompute()

    # Ruta A->B costo 1 (enlace directo), next hop = B
    assert dv.dv["B"]["cost"] == pytest.approx(1.0)
    assert dv.next_hop("B") == "B"


def test_indirect_route_via_neighbor():
    dv = DistanceVector()
    dv.on_init(me="A", neighbors=["B"])  # A no es vecino directo de C

    # B conoce a C con costo 1
    dv.on_info("B", {"vector": {"B": 0, "C": 1}})
    dv.recompute()

    # A deberia alcanzar C via B con costo 2 (=1+1)
    assert dv.dv["C"]["cost"] == pytest.approx(2.0)
    assert dv.next_hop("C") == "B"


def test_choose_better_neighbor_when_multiple():
    dv = DistanceVector()
    dv.on_init(me="A", neighbors=["B", "D"])

    # B conoce C con costo 3  -> A->B->C = 1+3 = 4
    dv.on_info("B", {"vector": {"B": 0, "C": 3}})
    # D conoce C con costo 1  -> A->D->C = 1+1 = 2  (mejor)
    dv.on_info("D", {"vector": {"D": 0, "C": 1}})
    dv.recompute()

    assert dv.dv["C"]["cost"] == pytest.approx(2.0)
    assert dv.next_hop("C") == "D"


def test_ignore_negative_costs_in_info():
    dv = DistanceVector()
    dv.on_init(me="A", neighbors=["B"])

    # B manda un costo negativo (debe ignorarse)
    dv.on_info("B", {"vector": {"C": -5, "B": 0}})
    dv.recompute()

    # No deberia aceptar ruta negativa hacia C
    # Si no existe entrada, se interpreta como infinito o sin ruta
    assert "C" not in dv.dv or math.isinf(dv.dv.get("C", {}).get("cost", float("inf")))
    assert dv.next_hop("C") is None


def test_build_info_exports_current_vector():
    dv = DistanceVector()
    dv.on_init(me="A", neighbors=["B"])
    dv.on_info("B", {"vector": {"B": 0, "C": 1}})
    dv.recompute()

    info = dv.build_info()
    assert "vector" in info
    vec = info["vector"]

    # Debe exportar costos finitos conocidos
    assert vec["A"] == pytest.approx(0.0)
    assert vec["B"] == pytest.approx(1.0)
    # Si el algoritmo ya calculo C, tambien puede anunciarlo
    assert vec.get("C", 2.0) == pytest.approx(2.0)
