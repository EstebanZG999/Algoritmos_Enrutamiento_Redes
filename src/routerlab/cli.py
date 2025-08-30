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
        choices=["flooding", "dvr"],   # habilitamos dvr ademas de flooding
        help="Protocolo de enrutamiento a usar",
    )
    p.add_argument(
        "--driver",
        required=True,
        choices=["socket"],            # xmpp llegara despues
        help="Transporte subyacente",
    )
    p.add_argument("--node", required=True, help="ID del nodo (p.ej. A)")
    p.add_argument("--topo", required=True, help="ruta a topo-*.json")
    p.add_argument("--names", required=True, help="ruta a names-*.json")
    p.add_argument("--port", type=int, required=True, help="puerto TCP local")
    args = p.parse_args()

    # Driver de red (TCP local)
    transport = SocketDriver(node=args.node, port=args.port, names_path=args.names)

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
        # Salida limpia con Ctrl+C
        pass

if __name__ == "__main__":
    main()
