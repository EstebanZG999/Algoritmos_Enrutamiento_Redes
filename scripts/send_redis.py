#!/usr/bin/env python3
import argparse
import asyncio
import json
import os
import uuid
from typing import Dict

from dotenv import load_dotenv
from redis.asyncio import Redis


def load_names(path: str) -> Dict[str, str]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("type") == "names", "names-redis.json inválido: falta type=names"
    config = data.get("config")
    assert isinstance(config, dict) and config, "names-redis.json inválido: campo config vacío"
    return config


def make_redis_client() -> Redis:
    """
    Crea un cliente Redis asíncrono.
    Prioriza REDIS_URL. Si no existe, arma a partir de host/port/password/tls.
    """
    url = os.getenv("REDIS_URL")
    if url:
        return Redis.from_url(url, decode_responses=False)

    host = os.getenv("REDIS_HOST", "127.0.0.1")
    port = int(os.getenv("REDIS_PORT", "6379"))
    db = int(os.getenv("REDIS_DB", "0"))
    password = os.getenv("REDIS_PASSWORD")
    tls = os.getenv("REDIS_TLS", "0") == "1"

    return Redis(
        host=host,
        port=port,
        db=db,
        password=password,
        ssl=tls,
        decode_responses=False,
    )


def build_wire(src: str, to: str, msg: str, proto: str = "flooding", mtype: str = "message", ttl: int = 8) -> Dict:
    """
    Construye el sobre (envelope) respetando el contrato del lab.
    """
    if ttl < 1:
        raise ValueError("TTL debe ser >= 1")
    if not src or not to:
        raise ValueError("src y to no pueden ser vacíos")

    return {
        "proto": proto,
        "type": mtype,
        "id": str(uuid.uuid4()),
        "from": src,
        "origin": src,
        "to": to,
        "ttl": int(ttl),
        "headers": [],
        "payload": msg,
    }


async def main():
    load_dotenv()

    ap = argparse.ArgumentParser(description="Inyecta un mensaje en Redis Pub/Sub para pruebas de routing.")
    ap.add_argument("--names", required=True, help="Ruta a names-redis.json (type=names, config={A:'router:A',...})")
    ap.add_argument("--src", required=True, help="Nodo origen lógico (A/B/C...)")
    ap.add_argument("--to", required=True, help="Destino lógico (A/B/C... o '*')")
    ap.add_argument("--msg", required=True, help="Payload a enviar")
    ap.add_argument("--proto", default="flooding", help="Protocolo (flooding|dvr|lsr|dijkstra). Default: flooding")
    ap.add_argument("--type", dest="mtype", default="message", help="Tipo de mensaje (message|info|hello|echo). Default: message")
    ap.add_argument("--ttl", type=int, default=8, help="TTL del mensaje. Default: 8")
    ap.add_argument("--direct", action="store_true",
                    help="Publica directamente en el canal del DESTINO (por defecto publica en el canal del ORIGEN).")
    args = ap.parse_args()

    names = load_names(args.names)

    # Canal objetivo según modo
    if args.direct:
        channel = names.get(args.to)
        if not channel:
            raise SystemExit(f"No encuentro canal para DESTINO={args.to} en {args.names}")
    else:
        channel = names.get(args.src)
        if not channel:
            raise SystemExit(f"No encuentro canal para ORIGEN={args.src} en {args.names}")

    wire = build_wire(src=args.src, to=args.to, msg=args.msg, proto=args.proto, mtype=args.mtype, ttl=args.ttl)

    r = make_redis_client()
    try:
        payload = json.dumps(wire, separators=(",", ":")).encode("utf-8")
        await r.publish(channel, payload)
        print(f"[OK] Publicado en canal '{channel}' → {wire['proto']}/{wire['type']} {wire['from']}→{wire['to']} (ttl={wire['ttl']})")
    finally:
        await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
