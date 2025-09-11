# src/routerlab/core/node.py
# Ciclo de vida del nodo (routing task + timers)
import json, asyncio, os
from typing import Dict, Any, Optional, Callable
from routerlab.core.forwarding import Forwarder
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

        self.HELLO_INTERVAL = int(os.getenv("HELLO_INTERVAL", "3"))
        self.INFO_INTERVAL  = int(os.getenv("INFO_INTERVAL",  "5"))

        # Estado de “suscripción”
        self._last_seen: Dict[str, float] = {}        # vecino -> ts del último hello/info
        self._active_neighbors: set[str] = set()      # vecinos confirmados (suscriptos)
        self.SUBSCRIBE_ACK = os.getenv("SUBSCRIBE_ACK", "1") == "1"  # responde hello inmediato

    async def _send_hello(self):
        """
        Envía mensajes tipo 'hello' a los vecinos inmediatos cada HELLO_INTERVAL segundos.
        Ahora solo envía hellos a vecinos que existen en la topología,
        y si hay lista de activos, solo a ellos.
        Formato:
        {
            "type": "hello",
            "from": nodo_origen,
            "to": vecino,
            "hops": peso
        }
        """
        while True:
            # Si ya tengo vecinos activos, saludo solo a ellos
            # Si no, saludo a todos los definidos en la topología
            destinos = list(self._active_neighbors) if self._active_neighbors else self.neighbors_list

            for nbr in destinos:
                metric = float(self.neighbors_costs.get(nbr, 1.0))
                msg = {
                    "type": "hello",
                    "from": self.id,
                    "to": nbr,
                    "hops": metric
                }
                await self.transport.send(nbr, json.dumps(msg))

            await asyncio.sleep(self.HELLO_INTERVAL)


    async def _send_info(self):
        """
        Propaga a los vecinos la información de costos como mensajes tipo 'message'.
        Ahora solo anuncia enlaces a vecinos que están activos (respondieron hello).
        Formato:
        {
            "type": "message",
            "from": nodo_origen,
            "to": vecino_destino,
            "hops": peso
        }
        """
        if not self.alg:
            return

        while True:
            # Solo usamos vecinos confirmados (activos), si no hay, usamos la lista base
            enlaces_confirmados = list(self._active_neighbors) if self._active_neighbors else []

            for nbr in self.neighbors_list:  # a quién envío mis mensajes
                for dest in enlaces_confirmados:
                    weight = self.neighbors_costs.get(dest, 1.0)
                    msg = {
                        "type": "message",
                        "from": self.id,
                        "to": dest,
                        "hops": float(weight)
                    }
                    await self.transport.send(nbr, json.dumps(msg))

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
                metric = evt.get("hops", 1.0)
                self._last_seen[src] = now

                # Si el algoritmo soporta marcar vecino activo
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
                self._last_seen[src] = now
                metric = evt.get("hops", 1.0)
                # pasa la info al algoritmo para actualizar la tabla
                if hasattr(self.alg, "on_message"):
                    self.alg.on_message(src, evt["to"], metric)
                self.alg.recompute()

            elif evt["type"] == "edge":
                u = evt["from"]   # quien me lo envió
                v = self.id       # yo
                w = float(self.neighbors_costs.get(u, evt.get("hops", 1.0)))
                if hasattr(self.alg, "on_edge_observed"):
                    if self.alg.on_edge_observed(u, v, w):
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
                # 👇 AQUI: parsea de string a dict
                import json
                if isinstance(msg, str):
                    try:
                        msg = json.loads(msg)
                    except Exception:
                        print(f"[{self.id}] drop invalid JSON: {msg}")
                        continue
                await self.forwarder.handle(msg)
        finally:
            for t in tasks:
                t.cancel()
