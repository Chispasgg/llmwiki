# 📚 LLM Wiki

[![Licencia](https://img.shields.io/badge/licencia-Apache%202.0-green)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-20+-black?logo=next.js)](https://nextjs.org/)

Fork local de [LLM Wiki](https://x.com/karpathy/status/2039805659525644595) ([spec original](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)), con mejoras de arquitectura, migración de herramientas y configuración centralizada.

Apunta el sistema a una carpeta con tus documentos, arranca la app local y conecta Claude vía MCP. Desde ahí, Claude lee tus fuentes, escribe páginas wiki y mantiene enlaces y citas en sincronía automáticamente.

![LLM Wiki — página wiki compilada con citas y tabla de contenidos](wiki-page.png)

---

## ¿Qué hace?

1. **📁 Tienes una carpeta** — PDFs, notas, artículos, hojas de cálculo. Tu investigación existente.
2. **🔍 LLM Wiki la indexa** — extrae texto, trocea para búsqueda, construye un índice SQLite local. Los archivos fuente no se tocan.
3. **🤖 Claude se conecta vía MCP** — lee fuentes, escribe páginas wiki en `wiki/`, mantiene referencias cruzadas y citas en notas al pie.
4. **📈 La wiki mejora sola** — a medida que Claude lee más del workspace y escribe más páginas, los resúmenes, páginas de entidades y referencias cruzadas se acumulan en lugar de derivarse desde cero en cada conversación.

---

## 🚀 Inicio rápido

**Requisitos:** Python 3.12+, Node.js 20+, [`uv`](https://astral.sh/uv)

```bash
git clone https://github.com/Chispasgg/llmwiki.git
cd llmwiki

# Instalar dependencias Python (API)
cd api && uv sync && cd ..

# Instalar dependencias Python (MCP)
cd mcp && uv sync && cd ..

# Instalar dependencias web
cd web && npm install && cd ..

# Inicializar un workspace (apunta a cualquier carpeta con tus archivos)
./llmwiki init ~/investigacion

# Arrancar la app
./llmwiki serve ~/investigacion
```

Abre [localhost:3000](http://localhost:3000). Los archivos están indexados y la wiki está lista.

---

## 🔌 Conectar Claude

```bash
./llmwiki mcp-config ~/investigacion
```

Imprime el fragmento JSON para `claude_desktop_config.json` (Claude Desktop) o `.claude/settings.json` (Claude Code). Cada workspace funciona como una entrada MCP independiente — si trabajas con varias carpetas de investigación, añade una entrada por carpeta.

Luego dile a Claude: *"Lee la guía, ingiere mis fuentes y empieza a construir la wiki."*

### Lanzador todo-en-uno

```bash
./llmwiki open ~/investigacion
```

Hace todo de una vez: inicializa si es necesario, arranca los servidores, abre el navegador e imprime el hint de configuración MCP.

#### Lanzador interactivo (multi-workspace)

Si tienes varios workspaces, usa el lanzador interactivo con configuración centralizada:

```bash
./launch_llmwiki.sh
```

Carga la configuración desde `config/llmwiki-launcher.conf`, lista los workspaces disponibles y permite elegir por número.

---

## 🌐 Acceso desde la red local (LAN)

El sistema detecta automáticamente la IP de la máquina y configura todos los servicios para ser accesibles desde cualquier dispositivo de la red.

### Web UI desde otro ordenador

```bash
# Con el lanzador (recomendado):
./launch_llmwiki.sh
# Imprime: Frontend: http://192.168.1.10:1504

# Con el CLI:
./llmwiki serve ~/investigacion
# Imprime: Web: http://192.168.1.10:1504
```

Para forzar una IP concreta, editar `config/llmwiki-launcher.conf`:
```bash
LAN_HOST="192.168.1.10"
```

O con el CLI:
```bash
./llmwiki serve --host 192.168.1.10 ~/investigacion
```

### MCP desde otro ordenador (Claude Desktop / Claude Code)

```bash
# Arrancar el servidor MCP en modo HTTP:
TRANSPORT=streamable-http ./start-mcp.sh ~/investigacion
# Escucha en 0.0.0.0:8765

# Ver la configuración para Claude:
./llmwiki mcp-config ~/investigacion
# Imprime opción A (stdio, local) y opción B (HTTP, red LAN)
```

En Claude Desktop / Claude Code del otro ordenador:
```json
{
  "mcpServers": {
    "llmwiki-investigacion": {
      "url": "http://192.168.1.10:8765/mcp"
    }
  }
}
```

Para activar MCP HTTP de forma permanente, editar `config/llmwiki-launcher.conf`:
```bash
MCP_TRANSPORT="streamable-http"
```

---

## 🖥️ CLI

| Comando | Descripción |
|---------|-------------|
| `llmwiki open <carpeta>` | Init + serve + abrir navegador |
| `llmwiki init <carpeta>` | Crear `.llmwiki/` + `wiki/`, indexar archivos existentes |
| `llmwiki serve <carpeta>` | Arrancar API en :8000 + web en :3000 |
| `llmwiki mcp <carpeta>` | Ejecutar servidor MCP stdio (para configuración de Claude) |
| `llmwiki mcp-config <carpeta>` | Imprimir fragmento `claude_desktop_config.json` |
| `llmwiki reindex <carpeta>` | Reconstruir el índice desde disco |

---

## 📂 Qué ocurre en disco

LLM Wiki añade dos cosas a tu carpeta. Los archivos fuente no se mueven ni modifican.

```
~/investigacion/              # Tus archivos existentes (intactos)
  papers/paper.pdf
  notas.md
  datos.xlsx
  wiki/                       # Páginas generadas (creadas por LLM Wiki)
    overview.md
    log.md
    conceptos/
      attention.md
  .llmwiki/                   # Índice + caché (oculto, reconstruible)
    index.db
    cache/
```

- `wiki/` — archivos markdown normales. Edítalos en cualquier editor. Claude los escribe y actualiza vía MCP.
- `.llmwiki/` — índice SQLite y artefactos procesados. Bórralo cuando quieras; `llmwiki reindex` lo reconstruye desde los archivos fuente.

Por defecto, indexación, almacenamiento y escritura de archivos ocurren en tu máquina. **No se requieren servicios cloud.**

---

## 🤖 Herramientas MCP disponibles para Claude

| Herramienta | Descripción |
|-------------|-------------|
| `guide` | Explica cómo funciona la wiki y lista el contenido del workspace |
| `search` | Navega archivos (`list`) o búsqueda de texto completo (`search`) |
| `read` | Lee documentos — PDFs con rangos de página, lecturas batch por glob |
| `write` | Crea páginas wiki, edita con `str_replace`, añade al final. Assets SVG/CSV |
| `delete` | Elimina documentos por ruta o patrón glob |

Todas las escrituras van a disco primero, luego actualizan el índice de búsqueda.

---

## 🏗️ Arquitectura

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Next.js    │────▶│   FastAPI    │────▶│   SQLite     │
│   Frontend   │     │   Backend    │     │   (local)    │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                     ┌──────┴───────┐
                     │  MCP Server  │◀──── Claude Desktop / Code
                     │   (stdio)    │
                     └──────────────┘
                            │
                     ┌──────┴───────┐
                     │  Filesystem  │  ← fuente de verdad
                     └──────────────┘
```

El filesystem es la fuente de verdad. SQLite es un índice derivado — acelera la búsqueda y almacena datos extraídos, pero siempre puede reconstruirse desde los archivos. Un file watcher en segundo plano detecta cambios realizados fuera de la app.

### Mejoras respecto al upstream

Esta versión incorpora las siguientes mejoras sobre el proyecto original:

- **📦 Migración a `uv` + `pyproject.toml`** — gestión de dependencias reproducible y rápida para API y MCP; eliminados `requirements.txt` y `requirements.lock`.
- **🔧 Configuración centralizada** — `api/config.py` con `pydantic-settings`; todos los parámetros configurables desde variables de entorno o `.env`.
- **🏗️ Startup modular** — separación limpia entre modo `local` (`api/startup/local.py`) y modo `hosted` (`api/startup/hosted.py`).
- **🔒 Mejoras de seguridad** — validación de entradas, gestión segura de secretos y cabeceras HTTP endurecidas.
- **🚀 `start-mcp.sh` mejorado** — script de arranque del servidor MCP con `uv sync` automático y logging estructurado.
- **🎛️ Lanzador interactivo** — `launch_llmwiki.sh` con configuración en `config/` para entornos multi-workspace.

---

## 📄 Procesamiento de documentos

Todo el procesamiento se ejecuta localmente. No se requieren claves API para uso básico.

| Formato | Parser | Notas |
|---------|--------|-------|
| PDF | opendataloader-pdf | Extracción de texto basada en Rust. Funciona bien para documentos de texto. |
| Markdown / Texto | nativo | Indexado y troceado directamente |
| HTML | BeautifulSoup | Elimina nav/anuncios, extrae markdown limpio |
| Excel / CSV | openpyxl | Extracción hoja a hoja |
| Imágenes | nativo | Almacenadas tal cual, visualizables inline |
| Word / PowerPoint | LibreOffice | Opcional. Instala LibreOffice para conversión de oficina; sin él, estos formatos se almacenan pero no se extraen. |

Configura `MISTRAL_API_KEY` para OCR de PDF de mayor calidad con mejor detección de tablas y maquetación.

---

## ⚙️ Variables de entorno

**API** (archivo `.env` en la raíz del proyecto):

```env
MODE=local                         # "local" o "hosted"
WORKSPACE_PATH=.                   # ruta al workspace (modo local)

# Modo hosted (opcional)
DATABASE_URL=postgresql://...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_JWT_SECRET=...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=tu-bucket

# Opcional
MISTRAL_API_KEY=                   # OCR avanzado para PDFs
CONVERTER_URL=                     # Conversión de archivos Office
LOGFIRE_TOKEN=                     # Observabilidad con Logfire
SENTRY_DSN=                        # Tracking de errores con Sentry
```

**Web** (variables de entorno Next.js):

```env
NEXT_PUBLIC_MODE=local
NEXT_PUBLIC_API_URL=http://localhost:8000
# Solo en modo hosted:
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=tu-anon-key
```

---

## ⚠️ Limitaciones

- **Un workspace = un servidor MCP.** Si trabajas con varios proyectos de investigación, cada uno tiene su propia carpeta y su propia entrada MCP. Es intencional — mantiene el contexto y el acceso a archivos acotado.
- **Extracción de tablas en PDF es aproximada.** opendataloader extrae prosa de forma fiable pero las tablas salen como texto desordenado. Para documentos financieros o PDFs con muchos datos, Mistral OCR es significativamente mejor.
- **LibreOffice añade fricción de configuración.** La conversión de archivos Office requiere una instalación local de LibreOffice. Si trabajas principalmente con PDFs y markdown, puedes omitirlo.
- **Sin búsqueda vectorial en modo local.** La búsqueda de texto completo usa SQLite FTS5 (porter stemming). Funciona bien para consultas por palabras clave pero no hace búsqueda semántica/embeddings.

---

## 🌐 Auto-hospedaje (versión multi-tenant)

Si quieres ejecutar la versión hospedada con Postgres, Supabase Auth y S3:

<details>
<summary>Instrucciones de configuración hospedada</summary>

### Requisitos previos

- Python 3.12+, Node.js 20+, `uv`
- Un proyecto [Supabase](https://supabase.com)
- Un bucket compatible con S3

### Base de datos

```bash
psql $DATABASE_URL -f supabase/migrations/001_initial.sql
```

### API

```bash
cd api
uv sync
MODE=hosted DATABASE_URL=postgresql://... uv run uvicorn main:app --port 8000
```

### Servidor MCP

```bash
cd mcp
uv sync
MODE=hosted DATABASE_URL=postgresql://... uv run uvicorn server:app --port 8080
```

### Web

```bash
cd web
npm install
NEXT_PUBLIC_MODE=hosted \
NEXT_PUBLIC_SUPABASE_URL=https://tu-ref.supabase.co \
NEXT_PUBLIC_SUPABASE_ANON_KEY=tu-anon-key \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
npm run dev
```

</details>

---

## 📜 Licencia

Apache 2.0 — ver [LICENSE](LICENSE)
