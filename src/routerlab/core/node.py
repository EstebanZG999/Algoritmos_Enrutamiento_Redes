# Ciclo de vida del nodo (routing task + timers)
import json, asyncio, os
from typing import Dict, Any, Optional, Callable
from routerlab.core.forwarding import Forwarder
from routerlab.core.messages import Message
from routerlab.algorithms.distance_vector import DistanceVector

def _load_topo(path: str) -> dict[str, list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("type") == "topo"
    return data["config"]

class RouterNode:
    def __init__(self, node_id: str, transport, topo_path: str, proto: str = "flooding"):
        self.id = node_id
        self.transport = transport
        topo = _load_topo(topo_path)
        self.neighbors = topo.get(self.id, [])
        self.proto = proto

        self.route_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

        if self.proto == "dvr":
            self.alg = DistanceVector()
            self.alg.on_init(self.id, self.neighbors)
            next_hop_func: Optional[Callable[[str], Optional[str]]] = self.alg.next_hop
        else:
            self.alg = None
            next_hop_func = None

        self.forwarder = Forwarder(
            send_func=self.transport.send,
            neighbors=self.neighbors,
            me=self.id,
            route_next_hop=next_hop_func,
            route_event_queue=self.route_queue,
        )

        self.HELLO_INTERVAL = int(os.getenv("HELLO_INTERVAL", "5"))
        self.INFO_INTERVAL  = int(os.getenv("INFO_INTERVAL",  "5"))

    async def _send_hello(self):
        while True:
            for nbr in self.neighbors:
                msg = Message(proto=self.proto, type="hello",
                              **{"from": self.id}, to=nbr,
                              payload={"metric": 1.0}, origin=self.id, via=self.id)
                await self.transport.send(nbr, msg.as_wire())
            await asyncio.sleep(self.HELLO_INTERVAL)

    async def _send_info(self):
        if not self.alg:
            return
        while True:
            payload = self.alg.build_info()
            for nbr in self.neighbors:
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
                self.alg.on_info(evt["from"], evt["payload"])
                self.alg.recompute()

    async def run(self):
        print(f"[{self.id}] up. neighbors={self.neighbors} addr={self.transport.me()} proto={self.proto}")
        tasks = [
            asyncio.create_task(self._routing_task()),
            asyncio.create_task(self._send_hello()),
            asyncio.create_task(self._send_info()),
        ]
        async for msg in self.transport.run():
            await self.forwarder.handle(msg)
        for t in tasks:
            t.cancel()
