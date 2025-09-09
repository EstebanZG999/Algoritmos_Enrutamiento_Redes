import redis

r = redis.Redis(
    host="homelab.fortiguate.com",
    port=16379,
    password="4YNydkHFPcayvlx7$zpKm",
    decode_responses=True  # para strings en lugar de bytes
)

try:
    pong = r.ping()
    print("Conexión OK:", pong)
except Exception as e:
    print("Error conectando:", e)
