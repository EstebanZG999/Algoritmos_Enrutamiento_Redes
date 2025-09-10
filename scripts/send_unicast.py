# Inyector unicast (driver=redis) para routerlab
import argparse, json, uuid
import redis
import pathlib

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names_json", help="Archivo JSON con mapeo de nombres a canales Redis")
    ap.add_argument("src", help="Nodo origen")
    ap.add_argument("to", help="Nodo destino")
    ap.add_argument("hops", type=float, help="Costo/peso de la arista")
    ap.add_argument("--proto", choices=["lsr","dijkstra","dvr","flooding"], default="lsr")
    ap.add_argument("--ttl", type=int, default=8)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=6379)
    args = ap.parse_args()

    # Cargar mapeo de canales
    cfg = json.loads(pathlib.Path(args.names_json).read_text(encoding="utf-8"))
    assert cfg.get("type") == "names", "names JSON inválido"
    chan = cfg["config"][args.src]  # Publicamos al canal del SRC

    # Construir mensaje en formato definido para flooding/link-state
    wire = {
        "proto": args.proto,
        "type": "message",
        "id": str(uuid.uuid4()),
        "from": args.src,
        "origin": args.src,
        "to": args.to,
        "ttl": int(args.ttl),
        "headers": [],
        "hops": float(args.hops)  # costo de la arista
    }

    # Publicar en Redis
    r = redis.Redis(host=args.host, port=args.port, decode_responses=True)
    r.publish(chan, json.dumps(wire))
    print(f"Publicado en canal '{chan}': {wire}")

if __name__ == "__main__":
    main()
