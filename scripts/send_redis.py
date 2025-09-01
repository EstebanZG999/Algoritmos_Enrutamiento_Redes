#!/usr/bin/env python3
import argparse, json, uuid, os, asyncio
from redis.asyncio import Redis

def load_names(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("type") == "names"
    return data["config"]

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", required=True, help="ruta a names-redis.json")
    ap.add_argument("--src", required=True, help="nodo origen lógico (A/B/C)")
    ap.add_argument("--to",  required=True, help="destino lógico (A/B/C o *)")
    ap.add_argument("--msg", required=True, help="payload a enviar")
    args = ap.parse_args()

    names = load_names(args.names)
    chan = names.get(args.src)
    if not chan:
        raise SystemExit(f"Canal no encontrado para SRC={args.src}")

    host = os.getenv("REDIS_HOST", "127.0.0.1")
    port = int(os.getenv("REDIS_PORT", "6379"))
    db   = int(os.getenv("REDIS_DB",   "0"))
    password = os.getenv("REDIS_PASSWORD", None)

    r = Redis(host=host, port=port, db=db, password=password, decode_responses=False)

    wire = {
        "proto": "flooding",
        "type": "message",
        "id": str(uuid.uuid4()),
        "from": args.src,
        "origin": args.src,
        "to": args.to,
        "ttl": 8,
        "headers": [],
        "payload": args.msg
    }
    await r.publish(chan, json.dumps(wire).encode("utf-8"))
    await r.aclose()
    print("enviado a canal", chan)

if __name__ == "__main__":
    asyncio.run(main())
