#!/usr/bin/env bash
cd "$(dirname $0)/.."

poetry run ruff check gitpkg --fix
poetry run ruff format gitpkg tests
