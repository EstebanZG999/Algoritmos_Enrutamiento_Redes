# Ciclo de vida del nodo
import json, asyncio
from typing import Dict, Any
from routerlab.core.forwarding import Forwarder

def _load_topo(path: str) -> dict[str, list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("type") == "topo"
    return data["config"]

class RouterNode:
    def __init__(self, node_id: str, transport, topo_path: str):
        self.id = node_id
        self.transport = transport
        topo = _load_topo(topo_path)
        # Solo usa la lista de vecinos, no se resuelven rutas globales
        self.neighbors = topo.get(self.id, [])
        self.forwarder = Forwarder(send_func=self.transport.send, neighbors=self.neighbors, me=self.id)

    async def run(self):
        print(f"[{self.id}] up. neighbors={self.neighbors} addr={self.transport.me()}")
        async for msg in self.transport.run():
            await self.forwarder.handle(msg)
