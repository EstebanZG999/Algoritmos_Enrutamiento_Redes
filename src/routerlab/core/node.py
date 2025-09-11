# src/routerlab/core/node.py
# Ciclo de vida del nodo (routing task + timers)
import json, asyncio, os
from typing import Dict, Any, Optional, Callable
from routerlab.core.forwarding import Forwarder
from routerlab.algorithms.distance_vector import DistanceVector
from routerlab.algorithms.dijkstra import Dijkstra
from routerlab.algorithms.link_state import LinkState
from routerlab.core.messages import make_hello, make_message, addr_to_node

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

        self.HELLO_INTERVAL = int(os.getenv("HELLO_INTERVAL", "3"))
        self.INFO_INTERVAL  = int(os.getenv("INFO_INTERVAL",  "5"))
        self.NEIGHBOR_DEAD = float(os.getenv("NEIGHBOR_DEAD", "5"))
        self.NODE_DEAD     = float(os.getenv("NODE_DEAD", "15"))

        # Estado de “suscripción”
        self._last_seen: Dict[str, float] = {}        # vecino -> ts del último hello/info
        self._active_neighbors: set[str] = set()      # vecinos confirmados (suscriptos)
        self.SUBSCRIBE_ACK = os.getenv("SUBSCRIBE_ACK", "1") == "1"  # responde hello inmediato

    async def _send_hello(self):
        """
        Envía HELLO a vecinos. Si hay vecinos activos, saluda solo a esos;
        si no, a todos los definidos en la topología.
        """
        while True:
            targets = list(self._active_neighbors) if self._active_neighbors else self.neighbors_list
            for nbr in targets:
                metric = float(self.neighbors_costs.get(nbr, 1.0))
                wire = make_hello(self.id, nbr, metric)
                await self.transport.send(nbr, wire)
            await asyncio.sleep(self.HELLO_INTERVAL)


    async def _send_info(self):
        """
        Propaga a los vecinos mis enlaces directos confirmados como mensajes 'message'.
        """
        if not self.alg:
            return
        while True:
            confirmed = list(self._active_neighbors) if self._active_neighbors else []
            for nbr in self.neighbors_list:
                for dest in confirmed:
                    weight = float(self.neighbors_costs.get(dest, 1.0))
                    wire = make_message(self.id, dest, weight)
                    await self.transport.send(nbr, wire)
            await asyncio.sleep(self.INFO_INTERVAL)
 
    async def _routing_task(self):
        loop = asyncio.get_event_loop()
        while True:
            evt = await self.route_queue.get()
            if not self.alg:
                continue

            now = loop.time()

            if evt["type"] == "hello":
                src = evt["from"]
                metric = float(evt.get("payload", {}).get("metric", 1.0))
                self._last_seen[src] = now

                changed = False
                if hasattr(self.alg, "mark_neighbor_active") and self.alg.is_neighbor_known(src):
                    if self.alg.mark_neighbor_active(src, metric):
                        changed = True
                        self._active_neighbors.add(src)
                        print(f"[{self.id}] subscribe: vecino {src} ACTIVO (metric={metric})")

                self.alg.on_hello(src, metric)
                if changed:
                    self.alg.recompute()

            elif evt["type"] == "message":
                src = evt["from"]
                dst = evt.get("to")
                hops = float(evt.get("hops", 1.0))

                now = loop.time()
                self._last_seen[src] = now
                if dst:
                    self._last_seen[dst] = now

                if hasattr(self.alg, "on_message"):
                    self.alg.on_message(src, dst, hops)
                self.alg.recompute()

    async def run(self):
        print(f"[{self.id}] up. neighbors={self.neighbors_costs if self.neighbors_costs else self.neighbors_list} addr={self.transport.me()} proto={self.proto}")
        tasks = [
            asyncio.create_task(self._routing_task()),
            asyncio.create_task(self._send_hello()),
            asyncio.create_task(self._send_info()),
            asyncio.create_task(self._aging_task()),
        ]
        try:
            async for raw in self.transport.run():
                if isinstance(raw, str):
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        # si llega basura, la ignoramos
                        continue
                elif isinstance(raw, dict):
                    msg = raw
                else:
                    continue

                # BYPASS forwarder para el modo 'socket' + mensajes simples
                t = msg.get("type")
                if t in ("hello", "message"):
                    if t == "hello":
                        await self.route_queue.put({
                            "type": "hello",
                            "from": addr_to_node(msg.get("from")),   # 👈 convertir a N#
                            "payload": {"metric": float(msg.get("hops", 1.0))}
                        })
                    else:
                        await self.route_queue.put({
                            "type": "message",
                            "from": addr_to_node(msg.get("from")),   # 👈 convertir a N#
                            "to":   addr_to_node(msg.get("to")),     # 👈 convertir a N#
                            "hops": float(msg.get("hops", 1.0))
                        })


        finally:
            for t in tasks:
                t.cancel()
    
    async def _aging_task(self):
        """
        Expira:
          - vecinos directos sin HELLO en NEIGHBOR_DEAD
          - nodos no vecinos sin INFO (LSP) en NODE_DEAD
        """
        loop = asyncio.get_event_loop()
        while True:
            now = loop.time()

            # Vecinos directos que expiraron por falta de HELLO
            expired_neighbors = [
                n for n in list(self._active_neighbors)
                if (now - self._last_seen.get(n, now)) > self.NEIGHBOR_DEAD
            ]
            for n in expired_neighbors:
                self._active_neighbors.discard(n)
                if hasattr(self.alg, "purge_node_everywhere") and self.alg.purge_node_everywhere(n):
                    print(f"[{self.id}] neighbor expired: {n} (>{self.NEIGHBOR_DEAD}s sin HELLO)")
                    self.alg.recompute()
            # Nodos no vecinos que expiraron por falta de INFO/LSP
            lsdb = getattr(self.alg, "lsdb", {}) or {}
            # Nodos que aparecen como 'from'
            keys_from = set(lsdb.keys())
            # Nodos que aparecen como 'to' dentro de cualquier entrada
            keys_to = set()
            for u, nbrs in lsdb.items():
                if isinstance(nbrs, dict):
                    keys_to.update(nbrs.keys())

            candidates = (keys_from | keys_to) - {self.id} - set(self.neighbors_list)

            expired_remote = [
                n for n in candidates
                if (now - self._last_seen.get(n, 0.0)) > self.NODE_DEAD
            ]
            for n in expired_remote:
                if hasattr(self.alg, "purge_node_everywhere") and self.alg.purge_node_everywhere(n):
                    print(f"[{self.id}] node expired: {n} (>{self.NODE_DEAD}s sin INFO)")
                    self.alg.recompute()

            await asyncio.sleep(1.0)
