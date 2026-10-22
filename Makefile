PY ?= python

.PHONY: setup bake dev test demo record lint

setup:
	$(PY) scripts/zill.py setup

bake:
	$(PY) scripts/zill.py bake

dev:
	$(PY) scripts/zill.py dev

test:
	$(PY) scripts/zill.py test

demo:
	$(PY) scripts/zill.py demo

record:
	$(PY) scripts/zill.py record

lint:
	$(PY) scripts/zill.py lint
