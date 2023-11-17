#!/usr/bin/env bash
set -e
cd "$(dirname $0)/.."

ruff check gitpkg
ruff format gitpkg --check --diff