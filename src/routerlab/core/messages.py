# src/routerlab/core/messages.py
from typing import Dict, Any

def _node_to_addr(node: str, group_prefix: str = "grupo") -> str:
    """
    Convierte 'N4' -> 'sec30.grupo4.nodo4'
    """
    n = int(node.replace("N", ""))
    return f"sec30.{group_prefix}{n}.nodo{n}"

def addr_to_node(addr: str) -> str:
    """
    Convierte 'sec30.grupo4.nodo4' -> 'N4'
    """
    try:
        last = addr.split(".")[-1]   # "nodo4"
        n = int(last.replace("nodo", ""))
        return f"N{n}"
    except Exception:
        return addr   # si ya está como "N#"


def make_hello(src: str, dst: str, hops: float, group_prefix: str = "grupo") -> Dict[str, Any]:
    """
    Construye un mensaje tipo 'hello'
    """
    return {
        "type": "hello",
        "from": _node_to_addr(src, group_prefix),
        "to": _node_to_addr(dst, group_prefix),
        "hops": float(hops)
    }

def make_message(src: str, dst: str, hops: float, group_prefix: str = "grupo") -> Dict[str, Any]:
    """
    Construye un mensaje tipo 'message'
    """
    return {
        "type": "message",
        "from": _node_to_addr(src, group_prefix),
        "to": _node_to_addr(dst, group_prefix),
        "hops": float(hops)
    }
