.PHONY: build install test typecheck package clean

build:
	poetry install

install:
	cp misc/aw-server.service /usr/lib/systemd/user/aw-server.service

test:
	python -c 'import aw_server'
	python -m pytest tests/test_server.py

typecheck:
	python -m mypy aw_server --ignore-missing-imports

package:
	python -m aw_server.__about__
	python -m PyInstaller aw-server.spec --clean --noconfirm

lint-fix:
	black .

clean:
	rm -rf build dist
	rm -rf aw_server/__pycache__
	rm -rf aw_server/static/*
	pip3 uninstall -y aw_server
	make --directory=aw-webui clean
