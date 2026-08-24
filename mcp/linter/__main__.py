"""CLI del linter: `python -m linter <kb-slug> [--workspace <path>]`.

Instancia el VaultFS apropiado según settings.MODE, resuelve la KB por slug,
ejecuta run_lint, imprime el informe y termina con exit code 1 si hay findings
cuya severidad supera el umbral definido en la política.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

_SEVERITY_ORDER = ("warning", "error")


def format_report(findings: list) -> str:
    """Formatea los findings agrupados por severidad.

    Cada línea sigue el patrón: SEV · check · page_path · reason → fix_hint
    """
    if not findings:
        return "No findings. Wiki looks clean."

    grouped: dict[str, list] = {}
    for f in findings:
        grouped.setdefault(f.severity, []).append(f)

    lines: list[str] = []
    # Muestra errores primero, luego warnings
    for sev in reversed(_SEVERITY_ORDER):
        if sev not in grouped:
            continue
        lines.append(f"\n[{sev.upper()}] ({len(grouped[sev])})")
        for f in grouped[sev]:
            lines.append(
                f"  {sev} · {f.check} · {f.page_path} · {f.reason} → {f.fix_hint}"
            )

    total = len(findings)
    lines.append(f"\nTotal: {total} finding(s)")
    return "\n".join(lines)


def exit_code(findings: list, fail_on: str) -> int:
    """Devuelve 1 si hay algún finding con severidad >= fail_on, 0 si no.

    Orden de severidad: warning < error.
    """
    fail_level = _SEVERITY_ORDER.index(fail_on) if fail_on in _SEVERITY_ORDER else 0
    for f in findings:
        sev = f.severity
        if sev in _SEVERITY_ORDER and _SEVERITY_ORDER.index(sev) >= fail_level:
            return 1
    return 0


async def _main_async(kb_slug: str, workspace: str | None) -> None:
    # Añade el directorio mcp/ al path para que los imports funcionen igual que
    # cuando se ejecuta desde mcp/
    mcp_dir = Path(__file__).resolve().parent.parent
    if str(mcp_dir) not in sys.path:
        sys.path.insert(0, str(mcp_dir))

    from config import settings
    from linter.policy import load_policy
    from linter.runner import run_lint

    if settings.MODE == "local":
        # Instanciación local: SqliteVaultFS (ver local_server.py líneas 57-60)
        import uuid

        ws_path = workspace or settings.WORKSPACE_PATH
        ws = Path(ws_path).resolve()

        from vaultfs import SqliteVaultFS

        await SqliteVaultFS.init(str(ws))

        user_id = os.environ.get(
            "LLMWIKI_USER_ID",
            str(uuid.uuid5(uuid.NAMESPACE_DNS, "local")),
        )
        fs = SqliteVaultFS(user_id)
    else:
        # Instanciación hosted: PostgresVaultFS (ver server_main.py línea 66 y
        # vaultfs/postgres.py líneas 1-16)
        from db import get_pool
        from vaultfs import PostgresVaultFS

        # En modo hosted se necesita un user_id real; se toma de la variable de
        # entorno que debería haber configurado el operador.
        user_id = os.environ.get("LLMWIKI_USER_ID")
        if not user_id:
            print(
                "Error: en modo hosted se requiere LLMWIKI_USER_ID para identificar al propietario de la KB.",
                file=sys.stderr,
            )
            sys.exit(2)

        # Inicializar el pool (necesario antes de usar PostgresVaultFS)
        await get_pool()
        fs = PostgresVaultFS(user_id)

    # Resolver KB por slug
    kb = await fs.resolve_kb(kb_slug)
    if not kb:
        print(f"Error: no se encontró la KB «{kb_slug}».", file=sys.stderr)
        sys.exit(2)

    kb_id: str = kb["id"]

    # Directorio de configuración de políticas
    config_dir = str(
        Path(__file__).resolve().parent.parent.parent.parent / "config" / "lint"
    )
    if not os.path.isdir(config_dir):
        # Fallback: usar el valor de settings si existe
        config_dir = settings.LINT_CONFIG_DIR

    findings = await run_lint(fs, kb_id, kb_slug, config_dir)
    policy = load_policy(kb_slug, config_dir)
    fail_on = policy.get("thresholds", {}).get("fail_on", "error")

    print(format_report(findings))
    sys.exit(exit_code(findings, fail_on))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m linter",
        description="Linter para knowledge bases de LLM Wiki.",
    )
    parser.add_argument("kb_slug", help="Slug de la knowledge base a analizar")
    parser.add_argument(
        "--workspace",
        default=None,
        help="Ruta al workspace (solo modo local; por defecto usa WORKSPACE_PATH del .env)",
    )
    args = parser.parse_args()
    asyncio.run(_main_async(args.kb_slug, args.workspace))


if __name__ == "__main__":
    main()
