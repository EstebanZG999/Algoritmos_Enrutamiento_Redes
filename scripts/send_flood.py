# scripts/send_flood.py
# Envia un mensaje tipo "message" (flooding) a un nodo local por TCP.
import json, socket, sys, uuid

# Uso: python scripts/send_flood.py <host> <port> <src> <to> <payload>
# Ej:   python scripts/send_flood.py 127.0.0.1 9101 A C "hola C, soy A!"
host, port, src, to, payload = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
msg = {
    "proto": "flooding",
    "type": "message",
    "id": str(uuid.uuid4()),
    "from": src,
    "origin": src,
    "to": to,
    "ttl": 8,
    "headers": [],
    "payload": payload
}
wire = (json.dumps(msg) + "\n").encode("utf-8")
s = socket.create_connection((host, port))
s.sendall(wire)
s.close()
print("enviado")
