FROM python:3.12.15-slim

RUN apt-get update \
    && apt-get install --no-install-recommends -y make \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
CMD ["make", "test"]
