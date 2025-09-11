# Inyector unicast (driver=socket) para routerlab
import argparse, json, socket, uuid

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("host")
    ap.add_argument("port", type=int)
    ap.add_argument("src")
    ap.add_argument("to")
    ap.add_argument("msg")
    ap.add_argument("--proto", choices=["dijkstra","dvr","flooding","lsr"], default="dijkstra")
    ap.add_argument("--ttl", type=int, default=8)
    args = ap.parse_args()

    wire = {
        "proto": args.proto,
        "type": "message",
        "id": str(uuid.uuid4()),
        "from": args.src,
        "origin": args.src,
        "to": args.to,
        "ttl": int(args.ttl),
        "headers": [],
        "payload": args.msg
    }

    with socket.socket() as s:
        s.connect((args.host, args.port))
        s.sendall((json.dumps(wire) + "\n").encode("utf-8"))
    print("enviado")

if __name__ == "__main__":
    main()
