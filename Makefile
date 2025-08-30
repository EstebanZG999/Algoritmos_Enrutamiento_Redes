PY=python3
VENV=.venv
PIP=$(VENV)/bin/pip
PYBIN=$(VENV)/bin/python

.PHONY: venv install run test
venv:
	$(PY) -m venv $(VENV)
install: venv
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt
run:
	PYTHONPATH=src $(PYBIN) -m routerlab.cli \
	  --proto=$(PROTO) --driver=socket --node=$(NODE) \
	  --topo=$(TOPO) --names=$(NAMES) --port=$(PORT)
send:
	$(PYBIN) scripts/send_flood.py 127.0.0.1 $(PORT) $(SRC) $(TO) "$(MSG)"