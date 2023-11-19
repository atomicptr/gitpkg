#!/usr/bin/env bash
cd "$(dirname $0)/.."

ruff check gitpkg --fix
ruff format gitpkg tests
