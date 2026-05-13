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

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless \
    tesseract-ocr \
    tesseract-ocr-spa \
    tesseract-ocr-eng \
    libreoffice-calc \
    libreoffice-impress \
    libreoffice-writer \
    ocrmypdf \
    pandoc \
    texlive-xetex \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    fonts-liberation \
    chromium \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2t64 \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Puppeteer debe usar el Chromium del sistema para evitar que descargue
# su propio binario, que fallaría en una imagen slim sin sandbox de red.
ENV PUPPETEER_SKIP_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

RUN npm install -g @mermaid-js/mermaid-cli@11.4.2

# En producción LATEX_TEMPLATE_PATH debe ser una ruta absoluta porque
# el proceso uvicorn puede tener un CWD distinto al esperado.
ENV LATEX_TEMPLATE_PATH=/app/config/wiki-export.tex

RUN useradd -m -u 1000 appuser

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser . .

USER appuser
ENV PATH="/app/.venv/bin:$PATH" MODE=hosted PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 1502
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "1502", "--timeout-graceful-shutdown", "30"]
