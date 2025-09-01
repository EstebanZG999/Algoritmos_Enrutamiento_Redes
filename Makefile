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
send:
	$(PYBIN) scripts/send_flood.py 127.0.0.1 $(PORT) $(SRC) '$(TO)' "$(MSG)"
send-redis:
	$(PYBIN) scripts/send_redis.py --names=$(NAMES) --src=$(SRC) --to=$(TO) --msg="$(MSG)"
broadcast:
	$(PYBIN) scripts/send_flood.py 127.0.0.1 $(PORT) $(SRC) '*' "$(MSG)"
test:
	PYTHONPATH=src $(PYBIN) -m pytest -q $(TEST) --ignore=docker --ignore=.venv --ignore=configs --ignore=scripts
