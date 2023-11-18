#!/usr/bin/env bash
set -e
cd "$(dirname $0)/.."

ruff check gitpkg --fix
ruff format gitpkg tests