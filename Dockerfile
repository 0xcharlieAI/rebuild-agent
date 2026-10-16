FROM python:3.12.15-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md Makefile ./
COPY src ./src
COPY tests ./tests

RUN apt-get update \
        && apt-get install -y --no-install-recommends patch make \
        && rm -rf /var/lib/apt/lists/*

RUN uv sync --frozen --dev

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["rebuild-agent"]
CMD ["--help"]
