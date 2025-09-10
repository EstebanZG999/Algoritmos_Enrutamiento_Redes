import json, asyncio, os
from typing import Dict, Any, Optional, Callable
from routerlab.core.forwarding import Forwarder
from routerlab.core.messages import Message, make_hello, make_message
from routerlab.algorithms.distance_vector import DistanceVector
from routerlab.algorithms.dijkstra import Dijkstra
from routerlab.algorithms.link_state import LinkState


def _load_topo(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("type") == "topo"
    return data["config"]


class RouterNode:
    def __init__(self, node_id: str, transport, topo_path: str, proto: str = "lsr"):
        self.id = node_id
        self.transport = transport
        topo = _load_topo(topo_path)

        # vecinos crudos: puede ser dict con pesos o lista
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
            self.alg.on_init(self.id, self.neighbors_costs)
            next_hop_func = self.alg.next_hop
        elif self.proto == "dijkstra":
            self.alg = Dijkstra(topo_path)
            self.alg.on_init(self.id, self.neighbors_list)
            next_hop_func = self.alg.next_hop
        elif self.proto == "lsr":
            self.alg = LinkState()
            self.alg.on_init(self.id, self.neighbors_costs)
            next_hop_func = self.alg.next_hop
        else:
            self.alg = None

        # Forwarder: siempre con lista de vecinos
        self.forwarder = Forwarder(
            send_func=self.transport.send,
            neighbors=self.neighbors_list,
            me=self.id,
            route_next_hop=next_hop_func,
            route_event_queue=self.route_queue,
        )

        self.HELLO_INTERVAL = int(os.getenv("HELLO_INTERVAL", "3"))

        # Estado de suscripción
        self._last_seen: Dict[str, float] = {}        # vecino -> timestamp del último hello
        self._active_neighbors: set[str] = set()
        self.SUBSCRIBE_ACK = os.getenv("SUBSCRIBE_ACK", "1") == "1"

    async def _send_hello(self):
        """
        Manda hello cada HELLO_INTERVAL segundos.
        """
        while True:
            msg = make_hello(self.id)  # 🔥 hello minimalista: {type:"hello"}
            for nbr in self.neighbors_list:
                await self.transport.send(nbr, msg.as_wire())
            await asyncio.sleep(self.HELLO_INTERVAL)

    async def _routing_task(self):
        loop = asyncio.get_event_loop()
        while True:
            evt = await self.route_queue.get()
            if not self.alg:
                continue

            now = loop.time()

            # Procesar HELLO
            if evt["type"] == "hello":
                src = evt["from"]  # el Forwarder agrega el remitente real
                metric = 1.0       # hello minimalista → costo fijo

                self._last_seen[src] = now

                if hasattr(self.alg, "mark_neighbor_active") and self.alg.is_neighbor_known(src):
                    if self.alg.mark_neighbor_active(src, metric):
                        self._active_neighbors.add(src)
                        print(f"[{self.id}] subscribe: vecino {src} ACTIVO (metric={metric})")

                        # 🔥 Solo floodear la primera vez que se descubre el vecino
                        if hasattr(self.alg, "on_message"):
                            adj_msg = make_message(self.id, src, metric)
                            await self.forwarder.handle(adj_msg.as_wire())

                self.alg.on_hello(src, metric)
                self.alg.recompute()

                if self.SUBSCRIBE_ACK:
                    ack = make_hello(self.id)
                    await self.transport.send(src, ack.as_wire())

            # Procesar MESSAGE (adyacencia)
            elif evt["type"] == "message":
                src = evt["from"]
                dst = evt["to"]
                hops = evt.get("hops", 1.0) or 1.0
                self._last_seen[src] = now
                if hasattr(self.alg, "on_message"):
                    self.alg.on_message(src, dst, hops)

    async def run(self):
        print(f"[{self.id}] up. neighbors={self.neighbors_costs if self.neighbors_costs else self.neighbors_list} addr={self.transport.me()} proto={self.proto}")
        tasks = [
            asyncio.create_task(self._routing_task()),
            asyncio.create_task(self._send_hello()),
        ]
        try:
            async for msg in self.transport.run():
                await self.forwarder.handle(msg)
        finally:
            for t in tasks:
                t.cancel()
