PY=python3
VENV=.venv
PIP=$(VENV)/bin/pip
PYBIN=$(VENV)/bin/python

DRIVER ?= socket

.PHONY: venv install run run-socket run-xmpp run-redis send broadcast test

venv:
	$(PY) -m venv $(VENV)
install: venv
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt
run: run-$(DRIVER)
run-socket:
	PYTHONPATH=src $(PYBIN) -m routerlab.cli \
	  --proto=$(PROTO) --driver=socket --node=$(NODE) \
	  --topo=$(TOPO) --names=$(NAMES) --port=$(PORT)
run-redis:
	PYTHONPATH=src $(PYBIN) -m routerlab.cli \
	  --proto=$(PROTO) --driver=redis --node=$(NODE) \
	  --topo=$(TOPO) --names=$(NAMES)


# ==== Parámetros por defecto para inyección ====
PORT ?= 9101
SRC  ?= A
TO   ?= C
MSG  ?= "hola desde routerlab"
TTL  ?= 8
NAMES ?= configs/names-redis.json

# ==== Socket (unicast) ====
send-dijkstra:
	$(PYBIN) scripts/send_unicast.py 127.0.0.1 $(PORT) $(SRC) $(TO) "$(MSG)" --proto dijkstra --ttl $(TTL)

send-dvr:
	$(PYBIN) scripts/send_unicast.py 127.0.0.1 $(PORT) $(SRC) $(TO) "$(MSG)" --proto dvr --ttl $(TTL)

send-flood:
	$(PYBIN) scripts/send_unicast.py 127.0.0.1 $(PORT) $(SRC) $(TO) "$(MSG)" --proto flooding --ttl $(TTL)

# ==== Redis (unicast) ====
send-redis-dijkstra:
	$(PYBIN) scripts/send_unicast_redis.py $(NAMES) $(SRC) $(TO) "$(MSG)" --proto dijkstra --ttl $(TTL)

send-redis-dvr:
	$(PYBIN) scripts/send_unicast_redis.py $(NAMES) $(SRC) $(TO) "$(MSG)" --proto dvr --ttl $(TTL)

send-redis-flood:
	$(PYBIN) scripts/send_unicast_redis.py $(NAMES) $(SRC) $(TO) "$(MSG)" --proto flooding --ttl $(TTL)

broadcast:
	$(PYBIN) scripts/send_flood.py 127.0.0.1 $(PORT) $(SRC) '*' "$(MSG)"
test:
	PYTHONPATH=src $(PYBIN) -m pytest -q $(TEST) --ignore=docker --ignore=.venv --ignore=configs --ignore=scripts
