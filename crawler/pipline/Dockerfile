FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app/crawler/pipline
COPY pyproject.toml uv.lock /app/crawler/pipline/
WORKDIR /app/crawler/pipline
RUN uv sync --frozen --no-cache --no-dev

COPY . /app/crawler/pipline

CMD ["uv", "run", "python", "-m", "crawler.pipline.cli", "run", "--source", "homepage"]
