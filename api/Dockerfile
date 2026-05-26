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
    texlive-plain-generic \
    texlive-fonts-recommended \
    fonts-liberation \
    fonts-ebgaramond \
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
    libasound2 \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Puppeteer debe usar el Chromium del sistema para evitar que descargue
# su propio binario, que fallaría en una imagen slim sin sandbox de red.
ENV PUPPETEER_SKIP_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

RUN npm install -g @mermaid-js/mermaid-cli@11.4.2

# Source Sans 3 (fontspec name "Source Sans 3") and Source Code Pro
# are not in Debian bookworm repos; install OTF files as system fonts.
# EB Garamond: the Google Fonts repo only has variable fonts; use fonttools
# to instantiate static variants with correct Name ID 1 so that fontconfig
# indexes them as "EB Garamond Bold" and XeTeX resolves BoldFont={EB Garamond Bold}.
COPY scripts/gen_eb_garamond.py /tmp/gen_eb_garamond.py
RUN pip install --quiet --target=/tmp/ft fonttools \
    && mkdir -p /usr/share/fonts/opentype/source-sans-3 \
                /usr/share/fonts/opentype/source-code-pro \
                /usr/share/fonts/truetype/eb-garamond-gf \
                /tmp/ebg \
    # Download EB Garamond variable fonts via raw.githubusercontent.com
    && curl -fsSL "https://raw.githubusercontent.com/google/fonts/main/ofl/ebgaramond/EBGaramond%5Bwght%5D.ttf" \
            -o /tmp/ebg/upright.ttf \
    && curl -fsSL "https://raw.githubusercontent.com/google/fonts/main/ofl/ebgaramond/EBGaramond-Italic%5Bwght%5D.ttf" \
            -o /tmp/ebg/italic.ttf \
    # Generate static instances (Regular/Bold/Italic/BoldItalic) with correct naming
    && python3 /tmp/gen_eb_garamond.py \
    # Source Sans 3
    && curl -fsSL "https://github.com/adobe-fonts/source-sans/releases/download/3.052R/OTF-source-sans-3.052R.zip" \
       -o /tmp/ss3.zip \
    && python3 -c "import zipfile,glob,shutil; z=zipfile.ZipFile('/tmp/ss3.zip'); z.extractall('/tmp/ss3'); [shutil.copy(p,'/usr/share/fonts/opentype/source-sans-3/') for p in glob.glob('/tmp/ss3/**/*.otf',recursive=True)]" \
    # Source Code Pro
    && curl -fsSL "https://github.com/adobe-fonts/source-code-pro/archive/refs/heads/release.tar.gz" \
       -o /tmp/scp.tar.gz \
    && python3 -c "import tarfile,glob,shutil; t=tarfile.open('/tmp/scp.tar.gz'); [t.extract(m,'/tmp/scp') for m in t.getmembers() if m.name.lower().endswith('.otf') and '/OTF/' in m.name]; [shutil.copy(p,'/usr/share/fonts/opentype/source-code-pro/') for p in glob.glob('/tmp/scp/**/*.otf',recursive=True)]" \
    && fc-cache -fv \
    && rm -rf /tmp/ft /tmp/ebg /tmp/gen_eb_garamond.py /tmp/ss3.zip /tmp/ss3 /tmp/scp.tar.gz /tmp/scp

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
