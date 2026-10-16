#!/usr/bin/env bash
set -Eeuo pipefail

cleanup() {
    if [[ -n "${TEMP_DIR:-}" && -d "$TEMP_DIR" ]]; then
        rm -rf "$TEMP_DIR"
    fi
}
trap cleanup EXIT

if ! command -v git >/dev/null 2>&1; then
    printf '%s\n' 'ERROR: git is required.' >&2
    exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
    printf '%s\n' 'ERROR: docker is required.' >&2
    exit 1
fi

REPOSITORY_ROOT="$(git rev-parse --show-toplevel)"
TEMP_DIR="$(mktemp -d)"
CLONE_DIR="$TEMP_DIR/rebuild-agent"
IMAGE="rebuild-agent-clean:${RANDOM}"

printf '%s\n' '==> Cloning repository into a temporary directory'
git clone --no-local "$REPOSITORY_ROOT" "$CLONE_DIR"

printf '%s\n' '==> Building Docker image from scratch'
docker build --pull --no-cache --tag "$IMAGE" "$CLONE_DIR"

printf '%s\n' '==> Running the test command in the container'
docker run --rm --entrypoint uv "$IMAGE" run pytest

printf '%s\n' '==> Running the report in the container'
docker run --rm --volume "$CLONE_DIR:/workspace:ro" --workdir /workspace \
    "$IMAGE" report /workspace --format markdown

printf '%s\n' '==> Clean-machine verification passed'
