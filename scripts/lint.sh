#!/usr/bin/env bash
set -e
cd "$(dirname $0)/.."

poetry run ruff check gitpkg
poetry run ruff format gitpkg --check --diff