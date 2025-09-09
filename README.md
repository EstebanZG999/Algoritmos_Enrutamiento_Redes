# Laboratorio – Algoritmos de Enrutamiento

Implementación modular de algoritmos de enrutamiento con dos “drivers” de red intercambiables:

- **`socket`**: TCP local (sin contenedores).
- **`redis`**: bus de mensajes usando Redis (Pub/Sub) vía Docker.

Algoritmos incluidos:

- **Flooding** (completo: demo funcional y pruebas).
- **Distance Vector (DVR)** mínimo (Bellman-Ford distribuido): convergencia simple entre 3 nodos.

La app levanta “routers” A/B/C que se comunican mediante el driver seleccionado. Cada router ejecuta un **forwarder** y, si el protocolo lo requiere, tareas periódicas de **HELLO/INFO** para intercambio de estado.

## Tabla de contenidos

1. [Estructura del repositorio](#estructura-del-repositorio)
2. [Requisitos](#requisitos)
3. [Instalación](#instalación)
4. [Archivos de configuración](#archivos-de-configuración)
5. [Ejecución](#ejecución)
   - [Opción A: TCP local (sin Docker)](#opción-a-tcp-local-sin-docker)
   - [Opción B: Redis (con Docker)](#opción-b-redis-con-docker)
6. [Algoritmos](#algoritmos)
7. [Formato de mensajes](#formato-de-mensajes)
8. [Scripts](#scripts)
9. [Pruebas (pytest)](#pruebas-pytest)

## Estructura del repositorio

```
Algoritmos_Enrutamiento_Redes/
├─ README.md
├─ Makefile
├─ requirements.txt
├─ docker-compose.yml                # Redis (prod/local)
├─ docker/
│  └─ redis/
│     └─ data/                       # datos AOF (bind mount)
├─ configs/
│  ├─ topo-sample.txt                # topología lógica A-B-C
│  ├─ names-sample.txt               # mapeo A/B/C -> host:port (driver=socket)
│  └─ names-redis.json               # mapeo A/B/C -> canal Redis (driver=redis)
├─ scripts/
│  ├─ send_flood.py                  # inyección de mensajes vía TCP (socket)
│  └─ send_redis.py                  # inyección de mensajes vía Redis Pub/Sub
├─ src/
│  └─ routerlab/
│     ├─ cli.py                      # launcher (--proto, --driver, ...)
│     ├─ algorithms/
│     │  ├─ base.py                  # contrato común (Protocol)
│     │  ├─ flooding.py              # flooding (lógica mínima)
│     │  └─ distance_vector.py       # DVR mínimo (Bellman-Ford distribuido)
│     ├─ core/
│     │  ├─ node.py                  # RouterNode + timers HELLO/INFO
│     │  ├─ forwarding.py            # manejo de DATA/TTL/dedupe + reenvío
│     │  └─ messages.py              # esquema/normalización de mensajes
│     └─ net/
│        ├─ transport.py             # interfaz abstracta Transport
│        ├─ socket_driver.py         # TCP local (127.0.0.1:puerto)
│        └─ redis_driver.py          # Redis (Pub/Sub)
└─ tests/
   ├─ test_flooding.py
   └─ test_distance_vector.py
```

## Requisitos

- Python 3.11+ (probado con 3.12).
- Docker + Docker Compose (para Redis).
- GNU Make.


## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
```

> Instala dependencias (incluye `redis` para el driver Redis y `pytest` para tests).

## Archivos de configuración

### 1) Topología

`configs/topo-sample.txt` (JSON válido en .txt):

```json
{ "type": "topo", "config": { "A": ["B","C"], "B": ["A","C"], "C": ["A","B"] } }
```

### 2) Nombres (driver=socket)

`configs/names-sample.txt`:

```json
{
  "type": "names",
  "config": {
    "A": "127.0.0.1:9101",
    "B": "127.0.0.1:9102",
    "C": "127.0.0.1:9103"
  }
}
```

### 3) Nombres (driver=redis)

`configs/names-redis.json`:

```json
{
  "type": "names",
  "config": {
    "A": "router:A",
    "B": "router:B",
    "C": "router:C"
  }
}
```

> En Redis, cada nodo escucha su **canal**. El driver publica en el canal del **destino**.

## Ejecución

Puedes correr **Flooding**, **DVR** o **Dijkstra** con cualquiera de los drivers.

### Opción A: TCP local (sin Docker)

Abrir **3 terminales** (una por nodo):

**Terminal A**
```bash
source .venv/bin/activate
make run DRIVER=socket PROTO=flooding NODE=A PORT=9101 TOPO=configs/topo-sample.txt NAMES=configs/names-sample.txt
```

**Terminal B**
```bash
source .venv/bin/activate
make run DRIVER=socket PROTO=flooding NODE=B PORT=9102 TOPO=configs/topo-sample.txt NAMES=configs/names-sample.txt
```

**Terminal C**
```bash
source .venv/bin/activate
make run DRIVER=socket PROTO=flooding NODE=C PORT=9103 TOPO=configs/topo-sample.txt NAMES=configs/names-sample.txt
```

Enviar mensajes (cuarta terminal):

```bash
# Flooding unicast A -> C
make send-flood PORT=9101 SRC=A TO=C MSG="hola C, vía Flooding socket!"

# DVR unicast A -> C
make send-dvr PORT=9101 SRC=A TO=C MSG="hola C, vía DVR socket!"

# Dijkstra unicast A -> C
make send-dijkstra PORT=9101 SRC=A TO=C MSG="hola C, vía Dijkstra socket!"

# Link State Routing A -> C
make send-lsr PORT=9101 SRC=A TO=C MSG="hola C, vía lsr socket!"


# Broadcast A -> todos (solo flooding)
make broadcast PORT=9101 SRC=A MSG="broadcast!"
```

> Para **DVR**, deja 5–10 s para que HELLO/INFO intercambien vectores antes de enviar mensajes.

---

### Opción B: Redis (con Docker)

1) Levantar Redis:

```bash
docker compose up -d
# verifica:
docker ps
docker exec -it algoritmos_enrutamiento_redes-redis-1 redis-cli ping  # PONG
```

2) Abrir **3 terminales**:

**A**
```bash
source .venv/bin/activate
make run DRIVER=redis PROTO=flooding NODE=A TOPO=configs/topo-sample.txt NAMES=configs/names-redis.json
```

**B**
```bash
source .venv/bin/activate
make run DRIVER=redis PROTO=flooding NODE=B TOPO=configs/topo-sample.txt NAMES=configs/names-redis.json
```

**C**
```bash
source .venv/bin/activate
make run DRIVER=redis PROTO=flooding NODE=C TOPO=configs/topo-sample.txt NAMES=configs/names-redis.json
```

3) Enviar mensajes (cuarta terminal):

```bash
# Flooding unicast A -> C
make send-redis-flood NAMES_REDIS=configs/names-redis.json SRC=A TO=C MSG="hola C, vía Redis Flooding!"

# DVR unicast A -> C
make send-redis-dvr NAMES_REDIS=configs/names-redis.json SRC=A TO=C MSG="hola C, vía Redis DVR!"

# Dijkstra unicast A -> C
make send-redis-dijkstra NAMES_REDIS=configs/names-redis.json SRC=A TO=C MSG="hola C, vía Redis Dijkstra!"

# Broadcast A -> todos (solo flooding)
make send-redis-flood NAMES_REDIS=configs/names-redis.json SRC=A TO='*' MSG="broadcast vía Redis!"
```


## Algoritmos

### Flooding
- Reenvía a **todos los vecinos** excepto el emisor anterior (`via` o `from`).
- Entrega local si `to == me` o si `to == "*"`. (Para depurar dejamos que el origen también “vea” su broadcast).
- **Deduplicación** por `id` con TTL en caché.
- Decrementa `ttl`; descarta si llega a 0.

### Distance Vector (DVR)
- **Bellman-Ford distribuido** con costo 1/vecino.
- Tareas periódicas:
  - `HELLO` a vecinos (confirma presencia/metric).
  - `INFO` con el vector actual (`{"vector": {dest: cost}}`).
- `Forwarder` reenvía **unicast** al `next_hop(dest)` calculado.

Seleccionas con `--proto=flooding` o `--proto=dvr`.

## Formato de mensajes

Ejemplo de **DATA**:

```json
{
  "proto": "flooding" "dvr",
  "type": "message" "hello" "info",
  "id": "<uuid4>",
  "from": "A",
  "origin": "A",
  "to": "C" "*",
  "ttl": 8,
  "headers": [],
  "payload": "hola C!"
}
```

- `origin`: primer emisor; se conserva a lo largo del camino.
- `via`: hop anterior (se usa internamente para evitar eco al emisor).

## Scripts

- `scripts/send_flood.py`: inyecta un mensaje “como si” llegara por socket al puerto del nodo origen.
- `scripts/send_redis.py`: publica un mensaje para que lo procese el driver Redis.

## Pruebas (pytest)

### A) Todo el set

```bash
make test
```

### B) Un archivo en particular

```bash
make test TEST=tests/test_distance_vector.py
```

## Roadmap / pendientes

- **Dijkstra**: algoritmo local (a partir de la topología).
- **Link State Routing (LSR)**: distribución de estados + Dijkstra por nodo.
- Métricas dinámicas por enlace (no siempre costo 1).
- Persistencia/telemetría de tablas de enrutamiento.
- Pruebas de integración extendidas (topologías más grandes).

### Créditos

Trabajo de laboratorio en tríos para la clase de Redes (2025).
Este repo incluye drivers pluggable (socket/redis) y dos algoritmos operativos (Flooding y DVR), con Makefile, scripts y pruebas automáticas.
