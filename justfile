default: help

help:
  @just --list --unsorted

install:
    uv sync --all-extras --dev

# build package
build:
  uv build

# run tests
test *ARGS:
  uv run -m pytest {{ARGS}}

# sanity checks
check: lint typecheck fmt-check test

lint *ARGS:
  uv run ruff check {{ARGS}}

fmt *ARGS:
  uv run ruff format {{ARGS}}

fmt-check *ARGS:
  uv run ruff format --check {{ARGS}}

format: fmt

typecheck:
  uv run ty check