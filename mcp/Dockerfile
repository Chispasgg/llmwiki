FROM python:3.12-slim-bookworm AS builder
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app

RUN useradd -m -u 1000 appuser

COPY --from=builder /app/.venv /app/.venv
COPY . .
RUN chown -R appuser:appuser /app

USER appuser
ENV PATH="/app/.venv/bin:$PATH" MODE=hosted PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 1501
CMD ["python", "server_main.py"]
