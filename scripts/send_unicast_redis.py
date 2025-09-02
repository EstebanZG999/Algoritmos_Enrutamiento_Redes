# Inyector unicast (driver=redis) para routerlab
import argparse, json, uuid
import redis

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names_json")
    ap.add_argument("src")
    ap.add_argument("to")
    ap.add_argument("msg")
    ap.add_argument("--proto", choices=["dijkstra","dvr","flooding"], default="dijkstra")
    ap.add_argument("--ttl", type=int, default=8)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=6379)
    args = ap.parse_args()

    # Cargar mapeo de canales
    import pathlib, json as _json
    cfg = _json.loads(pathlib.Path(args.names_json).read_text(encoding="utf-8"))
    assert cfg.get("type") == "names", "names JSON inválido"
    chan = cfg["config"][args.src]  # Publicamos al canal del SRC

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

    r = redis.Redis(host=args.host, port=args.port, decode_responses=True)
    r.publish(chan, json.dumps(wire))
    print(f"publicado en canal '{chan}'")

if __name__ == "__main__":
    main()
