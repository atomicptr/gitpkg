#!/usr/bin/env bash
set -e
cd "$(dirname $0)/.."

poetry run coverage run -m pytest