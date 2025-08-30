# CLI de arranque
import argparse, asyncio
from routerlab.net.socket_driver import SocketDriver
from routerlab.core.node import RouterNode

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--proto", required=True, choices=["flooding"])   # dvr/lsr/dijkstra luego
    p.add_argument("--driver", required=True, choices=["socket"])    # xmpp
    p.add_argument("--node", required=True)
    p.add_argument("--topo", required=True)
    p.add_argument("--names", required=True)
    p.add_argument("--port", type=int, required=True)
    args = p.parse_args()

    # TCP local
    transport = SocketDriver(node=args.node, port=args.port, names_path=args.names)
    node = RouterNode(node_id=args.node, transport=transport, topo_path=args.topo)

    asyncio.run(node.run())

if __name__ == "__main__":
    main()
