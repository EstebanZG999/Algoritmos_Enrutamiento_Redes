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
	$(PYBIN) -m routerlab.cli --proto=$(PROTO) --driver=socket --node=$(NODE) --topo=configs/topo-sample.json --names=configs/names-sample.json --port=$(PORT)
