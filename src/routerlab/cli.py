# src/routerlab/cli.py
# CLI de arranque (flooding | dvr) con driver socket/TCP
import argparse
import asyncio
from routerlab.net.socket_driver import SocketDriver
from routerlab.core.node import RouterNode

def main():
    p = argparse.ArgumentParser(prog="routerlab.cli")
    p.add_argument(
        "--proto",
        required=True,
        choices=["flooding", "dvr", "dijkstra","lsr"],
        help="Protocolo de enrutamiento a usar",
    )
    p.add_argument(
        "--driver",
        required=True,
        choices=["socket", "redis"],
        help="Transporte subyacente",
    )
    p.add_argument("--node", required=True, help="ID del nodo (p.ej. A)")
    p.add_argument("--topo", required=True, help="ruta a topo-*.json")
    p.add_argument("--names", required=True, help="ruta a names-*.json")
    p.add_argument("--port", type=int, default=0,
                   help="Solo para socket. En XMPP/Redis se ignora.")
    args = p.parse_args()

    # Driver de red (TCP local)
    if args.driver == "socket" and (not args.port or args.port <= 0):
        p.error("--port es requerido y debe ser > 0 con --driver=socket")

    if args.driver == "socket":
        transport = SocketDriver(node=args.node, port=args.port, names_path=args.names)
    elif args.driver == "xmpp":
        from routerlab.net.xmpp_driver import XMPPDriver
        transport = XMPPDriver(node=args.node, names_path=args.names)
    elif args.driver == "redis":
        from routerlab.net.redis_driver import RedisDriver
        transport = RedisDriver(node=args.node, names_path=args.names)
    else:
        raise ValueError("driver no soportado")

    # Router con el protocolo seleccionado
    node = RouterNode(
        node_id=args.node,
        transport=transport,
        topo_path=args.topo,
        proto=args.proto,
    )

    try:
        asyncio.run(node.run())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
