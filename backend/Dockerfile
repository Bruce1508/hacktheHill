FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --uid 1000 app
USER app

CMD ["uvicorn", "backtrace.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
