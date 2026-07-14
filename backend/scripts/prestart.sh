#! /usr/bin/env bash

set -e
set -x

# Let the DB start
python -m app.scripts.backend_pre_start

# Run migrations
alembic upgrade head

# Create initial data in DB
python -m app.scripts.initial_data
