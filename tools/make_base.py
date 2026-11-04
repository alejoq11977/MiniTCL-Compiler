"""Reconstruye el cuaderno base (material suministrado) desde el cuaderno actual.

Este script es de un solo uso: deja ``tools/notebook_base.ipynb``, que es el
cuaderno tal como lo entregó el curso (con las celdas de código sustituidas
por las versiones completas, que ``tools/build_notebook.py`` regenera a partir
de los módulos).  A partir de ese base, el constructor es idempotente.

Uso::

    python3 tools/make_base.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = ROOT / "MiniTcl_Analizador_Descendente_Recursivo_Guia_Estudiante.ipynb"
BASE = ROOT / "tools" / "notebook_base.ipynb"

GENERATED = re.compile(r"^# === (MODULE|NOTEBOOK):")

# Celdas del material sustituidas por la implementación completa.
SUPERSEDED = [
    "# === MODULE: model.py | PARTE 1/2 ===",
    "# === MODULE: model.py | PARTE 2/2 ===",
    "# === MODULE: script_parser.py | PARTE 1/1 ===",
    "# === MODULE: expr_parser.py | PARTE 1/1 ===",
    "# --- Las dos fachadas públicas ---",
]

MD_10 = """## 10. Esqueleto del parser: completar desde la gramática

Solo se resuelve el caso de una palabra que consta de **un `TEXT`**. Se deja implementada la coordinación básica de scripts y comandos para mostrar el uso del cursor. El estudiante debe ampliar `parse_word`, desarrollar los métodos pendientes y escribir el lexer.

El argumento `stop` fija el fin del contexto, pero no consume ese token. En particular, el analizador exterior exige `EOF` y el de sustitución deberá exigir `RBRACKET`. Cada iteración de un bucle tiene que consumir al menos un token o terminar: un error habitual es quedar atrapado en un bucle infinito.
"""

MD_11 = """## 11. Contratos de los métodos pendientes

| Método | Entrada / decisión | Salida y obligación |
|---|---|---|
| `parse_word` | Mirar primer token | Elegir `BRACED`, `QOPEN` o palabra no agrupada |
| `parse_bare_word` | `TEXT`, `VAR` o `LBRACKET` | Acumular partes hasta que deje de comenzar una parte; no consumir separador |
| `parse_quoted_word` | `QOPEN` | Admitir cero partes; exigir `QCLOSE`; rechazar texto adyacente tras el cierre |
| `parse_braced_word` | `BRACED` | Un `Word(mode='braced')` con un solo `Literal`; no interpretar su contenido |
| `parse_part` | Primera clase de fragmento | Producir `Literal`, `Variable` o `CommandSubstitution` |
| `parse_substitution` | `LBRACKET` | Llamar a `parse_script(stop='RBRACKET')`, consumir cierre y construir nodo |
| `parse_command` | Inicio de palabra | Acumular palabras separadas por `WS`; no confundir partes contiguas con argumentos |

### Puntos de predicción que debe justificar

- `FIRST(word) = {BRACED, QOPEN, TEXT, VAR, LBRACKET}`.
- `FIRST(part) = {TEXT, VAR, LBRACKET}`.
- Después de `QOPEN`, `QCLOSE` permite una palabra vacía.
- Después de `WS` en un comando, mirar si empieza otra palabra; de lo contrario el espacio es final.
- Después de `LBRACKET`, un `RBRACKET` inmediato admite un script vacío.

**Actividad escrita:** explique por qué el modo del lexer forma parte del contrato. No declare que toda la sintaxis de Tcl es una gramática LL(1) sobre caracteres sin mostrar cómo se tokenizan los contextos.
"""

CODE_16 = """# Tokens MANUALES: esta celda no sustituye el trabajo del lexer.
# Fuente equivalente: set x 10; puts hola
starter_tokens = [
    Token("TEXT", "set", Span(0, 3)), Token("WS", " ", Span(3, 4)),
    Token("TEXT", "x", Span(4, 5)), Token("WS", " ", Span(5, 6)),
    Token("TEXT", "10", Span(6, 8)), Token("SEP", ";", Span(8, 9)),
    Token("WS", " ", Span(9, 10)), Token("TEXT", "puts", Span(10, 14)),
    Token("WS", " ", Span(14, 15)), Token("TEXT", "hola", Span(15, 19)),
    Token("EOF", "", Span(19, 19)),
]
starter_ast = ScriptParser(starter_tokens).parse()
assert len(starter_ast.commands) == 2
assert starter_ast.commands[0].words[2].parts[0].text == "10"
show_ast(starter_ast)
"""


def markdown_cell(source: str):
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }


def code_cell(source: str):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


def main() -> int:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    cells = []
    for cell in notebook["cells"]:
        source = "".join(cell["source"])
        if source.startswith("## 21.") or source.startswith("### 21."):
            continue  # celdas de respuestas: las regenera el constructor
        if source.startswith("## 21. Entrega"):
            continue
        first = source.split("\n", 1)[0].strip()
        if GENERATED.match(first):
            continue  # celdas generadas: las regenera el constructor
        if any(source.startswith(prefix) for prefix in SUPERSEDED):
            continue
        if source.startswith("# SLY es necesario para la parte de expr"):
            continue  # celda de comprobación de SLY: la regenera el constructor
        cells.append(cell)

    # Restaurar las celdas del material que el constructor anterior sustituyó.
    restored = []
    for cell in cells:
        source = "".join(cell["source"])
        restored.append(cell)
        if source.startswith("## 9. Infraestructura mínima"):
            restored.append(markdown_cell(MD_10))
            restored.append(code_cell(CODE_16))
            restored.append(markdown_cell(MD_11))

    notebook["cells"] = restored
    BASE.write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"Base escrito: {BASE.relative_to(ROOT)} ({len(restored)} celdas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
