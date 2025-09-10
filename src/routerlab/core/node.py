# src/routerlab/core/node.py
# Ciclo de vida del nodo (routing task + timers)
import json, asyncio, os
from typing import Dict, Any, Optional, Callable
from routerlab.core.forwarding import Forwarder
from routerlab.core.messages import Message
from routerlab.algorithms.distance_vector import DistanceVector
from routerlab.algorithms.dijkstra import Dijkstra
from routerlab.algorithms.link_state import LinkState

def _load_topo(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("type") == "topo"
    return data["config"]

class RouterNode:
    def __init__(self, node_id: str, transport, topo_path: str, proto: str = "flooding"):
        self.id = node_id
        self.transport = transport
        topo = _load_topo(topo_path)

        # neighbors_raw puede ser list[str] o dict[str, float]
        neighbors_raw = topo.get(self.id, [])
        if isinstance(neighbors_raw, dict):
            self.neighbors_costs: Dict[str, float] = {n: float(w) for n, w in neighbors_raw.items()}
            self.neighbors_list: list[str] = list(neighbors_raw.keys())
        else:
            self.neighbors_list = list(neighbors_raw)
            self.neighbors_costs = {n: 1.0 for n in self.neighbors_list}

        self.proto = proto
        self.route_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

        # Selección de algoritmo
        next_hop_func: Optional[Callable[[str], Optional[str]]] = None
        if self.proto == "dvr":
            self.alg = DistanceVector()
            # DV agradece costos directos si existen
            self.alg.on_init(self.id, self.neighbors_costs)
            next_hop_func = self.alg.next_hop
        elif self.proto == "dijkstra":
            # Si tu Dijkstra necesita el grafo global por path, déjalo como estaba;
            # si solo requiere vecindad, también puede usar neighbors_list.
            self.alg = Dijkstra(topo_path)
            self.alg.on_init(self.id, self.neighbors_list)
            next_hop_func = self.alg.next_hop
        elif self.proto == "lsr":
            self.alg = LinkState()
            # LinkState acepta list o dict; le pasamos dict (costos reales)
            self.alg.on_init(self.id, self.neighbors_costs)
            next_hop_func = self.alg.next_hop
        else:
            self.alg = None

        # Forwarder SIEMPRE recibe lista de vecinos (para flooding / envío)
        self.forwarder = Forwarder(
            send_func=self.transport.send,
            neighbors=self.neighbors_list,
            me=self.id,
            route_next_hop=next_hop_func,
            route_event_queue=self.route_queue,
        )

        self.HELLO_INTERVAL = int(os.getenv("HELLO_INTERVAL", "5"))
        self.INFO_INTERVAL  = int(os.getenv("INFO_INTERVAL",  "5"))

    async def _send_hello(self):
        """
        En topo ponderado, envía metric = costo real del enlace.
        """
        while True:
            for nbr in self.neighbors_list:
                metric = float(self.neighbors_costs.get(nbr, 1.0))
                msg = Message(proto=self.proto, type="hello",
                              **{"from": self.id}, to=nbr,
                              payload={"metric": metric}, origin=self.id, via=self.id)
                await self.transport.send(nbr, msg.as_wire())
            await asyncio.sleep(self.HELLO_INTERVAL)

    async def _send_info(self):
        """
        Anuncia estado de ruteo:
          - LSR: payload={"lsp": alg.build_info()}  (interoperable)
          - Otros: payload = alg.build_info()
        """
        if not self.alg:
            return
        while True:
            payload = self.alg.build_info()
            if self.proto == "lsr" and "lsp" not in payload:
                payload = {"lsp": payload}
            for nbr in self.neighbors_list:
                msg = Message(proto=self.proto, type="info",
                              **{"from": self.id}, to=nbr,
                              payload=payload, origin=self.id, via=self.id)
                await self.transport.send(nbr, msg.as_wire())
            await asyncio.sleep(self.INFO_INTERVAL)

    async def _routing_task(self):
        while True:
            evt = await self.route_queue.get()
            if not self.alg:
                continue
            if evt["type"] == "hello":
                self.alg.on_hello(evt["from"], evt["payload"].get("metric", 1.0))
                self.alg.recompute()
            elif evt["type"] == "info":
                # Pasa tal cual (LSR sabrá leer payload["lsp"] o payload["lsdb"])
                self.alg.on_info(evt["from"], evt["payload"])
                self.alg.recompute()

    async def run(self):
        print(f"[{self.id}] up. neighbors={self.neighbors_costs if self.neighbors_costs else self.neighbors_list} addr={self.transport.me()} proto={self.proto}")
        tasks = [
            asyncio.create_task(self._routing_task()),
            asyncio.create_task(self._send_hello()),
            asyncio.create_task(self._send_info()),
        ]
        try:
            async for msg in self.transport.run():
                await self.forwarder.handle(msg)
        finally:
            for t in tasks:
                t.cancel()
