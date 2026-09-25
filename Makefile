PYTHON ?= python

.PHONY: install download-data build test samples
install:
	$(PYTHON) -m pip install -r requirements.txt

download-data:
	$(PYTHON) scripts/download_osm_data.py --regions kanto chubu --snapshot 260923 --manifest data/processed/manifest.json

build:
	$(PYTHON) -m src.main build data/raw/kanto-260923.osm.pbf data/raw/chubu-260923.osm.pbf --bbox 138.25 34.75 141.25 37.25

test:
	$(PYTHON) -m pytest -q

samples:
	$(PYTHON) -m scripts.run_samples --check
