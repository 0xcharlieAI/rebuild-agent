# rebuild-agent

## What it does

`rebuild-agent` is a CLI tool for analyzing a software project and making its
development and runtime environment reproducible. It will grow to propose and
verify fixes with an AI agent.

## Requirements

- Linux or another system capable of running Python 3.12.
- [uv](https://docs.astral.sh/uv/) for Python environments and dependencies.
- Docker, only when using the Docker workflow.

The repository pins Python to 3.12 in `.python-version` and constrains the
package to Python 3.12 in `pyproject.toml`.

## Setup

From the repository root, create the locked development environment:

```sh
uv sync --locked --dev
```

No API key is required for the current CLI. If a later feature needs one,
copy `.env.example` to `.env` and replace its placeholder locally. Do not
commit `.env` or real credentials.

## Run

Run the CLI through the uv-managed environment:

```sh
uv run rebuild-agent --help
```

## Test

The single supported test command is:

```sh
uv run pytest
```

The equivalent Make target is:

```sh
make test
```

The test suite includes a repository path check that rejects machine-specific
Unix home-directory paths and Windows drive-root paths.

## Docker usage

Build the image from the repository root and run the CLI help command:

```sh
docker build -t rebuild-agent .
docker run --rm rebuild-agent --help
```

The Dockerfile uses the exact Python `3.12.15-slim` image and installs the
application from `uv.lock` with `uv sync --frozen --dev`.

## Verify

Run the clean-machine verification script from the repository root. It clones
the repository into a temporary directory, builds the Docker image without
cache, runs the test command in the container, and runs the report there:

```sh
bash scripts/verify_clean.sh
```
