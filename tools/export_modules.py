"""Exporta los módulos del proyecto a partir del cuaderno.

El cuaderno es la fuente de verdad: las celdas de código llevan la marca

    # === MODULE: <ruta del módulo> | PARTE <n>/<m> ===

y este script concatena las partes de cada módulo, les antepone el bloque de
imports que corresponde (los que en el cuaderno no hacen falta porque las
celdas anteriores ya definieron esos nombres) y escribe el fichero.

Uso::

    python3 tools/export_modules.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from layout import MODULES  # noqa: E402

NOTEBOOK = ROOT / "MiniTcl_Analizador_Descendente_Recursivo_Guia_Estudiante.ipynb"

MARKER = re.compile(r"^# === MODULE: (?P<name>.+?) \| PARTE (?P<index>\d+)/(?P<total>\d+) ===$")
DOCSTRING = re.compile(r'\A(""".*?"""|\'\'\'.*?\'\'\')\n', re.DOTALL)


def split_imports(text: str) -> tuple[str, str]:
    """Separa el bloque de imports inicial del resto del texto."""
    lines = text.split("\n")
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    depth = 0
    end = index
    seen = False
    while end < len(lines):
        line = lines[end]
        stripped = line.strip()
        if depth > 0:
            depth += line.count("(") - line.count(")")
            end += 1
            continue
        if stripped.startswith("import ") or stripped.startswith("from "):
            depth += line.count("(") - line.count(")")
            seen = True
            end += 1
            continue
        if not stripped and seen:
            end += 1
            continue
        break
    return "\n".join(lines[:end]), "\n".join(lines[end:])


def place_prefix(prefix: str, body: str) -> str:
    """Coloca los imports del proyecto tras el bloque de imports del módulo.

    Así ``from __future__ import annotations`` sigue siendo la primera
    sentencia del fichero y los imports del proyecto quedan agrupados.
    """
    if not prefix:
        return body
    match = DOCSTRING.match(body)
    if match is None:
        head, rest = "", body
    else:
        head, rest = body[: match.end()], body[match.end():]
    imports, code = split_imports(rest)
    if not imports.strip():
        return head + prefix + "\n" + rest
    return head + "\n" + imports.rstrip("\n") + "\n\n" + prefix + "\n" + code.lstrip("\n")


def main() -> int:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    collected: dict[str, dict[int, str]] = {}
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        first, _, rest = source.partition("\n")
        match = MARKER.match(first.strip())
        if match is None:
            continue
        name = match.group("name")
        index = int(match.group("index"))
        collected.setdefault(name, {})[index] = rest

    for name, config in MODULES.items():
        parts = collected.get(name)
        if not parts:
            print(f"AVISO: el cuaderno no contiene el módulo {name}")
            continue
        total = config["parts"]
        if sorted(parts) != list(range(1, total + 1)):
            print(f"AVISO: {name} tiene partes {sorted(parts)}, se esperaban {total}")
            continue
        body = "".join(parts[index] for index in range(1, total + 1))
        target = ROOT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        content = place_prefix(config["prefix"], body) + config.get("suffix", "")
        target.write_text(content, encoding="utf-8")
        print(f"exportado {name}")

    print("Módulos exportados desde el cuaderno.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
