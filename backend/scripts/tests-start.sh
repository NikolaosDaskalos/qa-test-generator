#! /usr/bin/env bash
set -e
set -x

python -m app.scripts.tests_pre_start

bash scripts/test.sh "$@"
