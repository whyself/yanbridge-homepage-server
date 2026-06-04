FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --no-dev
RUN uv run crawl4ai-setup && uv run playwright install --with-deps chromium

COPY homepage_crawler ./homepage_crawler
COPY config ./config

CMD ["uv", "run", "python", "-m", "homepage_crawler.main"]
