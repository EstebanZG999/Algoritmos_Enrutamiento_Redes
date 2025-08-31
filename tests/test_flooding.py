# Tests para FloodingAlgo
import uuid
from routerlab.algorithms.flooding import FloodingAlgo

def new_id():
    return str(uuid.uuid4())

def test_deliver_and_forward_basic():
    f = FloodingAlgo(me="B", neighbors=["A", "C"])
    msg = {
        "id": new_id(), "proto":"flooding", "type":"message",
        "from":"A", "to":"C", "ttl": 3, "headers":[], "payload":"hi", "via":"A"
    }
    d = f.handle(msg)
    assert d["reason"] == "ok"
    assert d["deliver"] is False           # B no es destino
    assert "A" not in d["outgoing"]        # anti-eco: no reenvia a A
    assert d["outgoing"] == ["C"]          # reenvia solo a C
    assert d["wire"]["ttl"] == 2
    assert d["wire"]["from"] == "B"
    assert d["wire"]["via"]  == "B"

def test_deliver_broadcast():
    f = FloodingAlgo(me="B", neighbors=["A", "C"])
    msg = {
        "id": new_id(), "proto":"flooding", "type":"message",
        "from":"A", "to":"*", "ttl": 2, "headers":[], "payload":"broadcast", "via":"A"
    }
    d = f.handle(msg)
    assert d["deliver"] is True            # B entrega local por '*'
    assert "A" not in d["outgoing"]        # no eco a A
    assert set(d["outgoing"]) == {"C"}     # solo a C (sus vecinos)
    assert d["wire"]["ttl"] == 1

def test_ttl_zero_drops():
    f = FloodingAlgo(me="B", neighbors=["A", "C"])
    msg = {
        "id": new_id(), "proto":"flooding", "type":"message",
        "from":"A", "to":"C", "ttl": 0, "headers":[], "payload":"x", "via":"A"
    }
    d = f.handle(msg)
    assert d["reason"] == "ttl_expired"
    assert d["wire"] is None
    assert d["outgoing"] == []

def test_duplicate_drop():
    f = FloodingAlgo(me="B", neighbors=["A", "C"])
    mid = new_id()
    msg = {
        "id": mid, "proto":"flooding", "type":"message",
        "from":"A", "to":"C", "ttl": 3, "headers":[], "payload":"x", "via":"A"
    }
    first = f.handle(msg)
    dup = f.handle(msg)  # mismo id
    assert first["reason"] == "ok"
    assert dup["reason"] == "duplicate"
    assert dup["outgoing"] == []
