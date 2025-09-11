# src/routerlab/core/messages.py
from typing import Dict, Any

def make_hello(src: str, dst: str, hops: float) -> Dict[str, Any]:
    """
    Construye un mensaje tipo 'hello'
    """
    return {
        "type": "hello",
        "from": src,
        "to": dst,
        "hops": float(hops)
    }

def make_message(src: str, dst: str, hops: float) -> Dict[str, Any]:
    """
    Construye un mensaje tipo 'message'
    """
    return {
        "type": "message",
        "from": src,
        "to": dst,
        "hops": float(hops)
    }
