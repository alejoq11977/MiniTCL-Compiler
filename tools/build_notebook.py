"""Construye el cuaderno del estudiante a partir de los módulos entregados.

El cuaderno es la fuente de verdad de la entrega.  Este script parte del
material suministrado (``tools/notebook_base.ipynb``), inserta las celdas de
código con la implementación completa —marcadas con
``# === MODULE: <fichero> | PARTE n/m ===``— y añade las celdas de markdown con
las respuestas escritas a las actividades y a las ocho preguntas.

La construcción es **determinista e idempotente**: siempre se parte del base,
de modo que ejecutarlo dos veces produce el mismo cuaderno.

Uso::

    python3 tools/build_notebook.py
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from layout import CUTS, MODULES  # noqa: E402

import re

DOCSTRING = re.compile(r'\A(""".*?"""|\'\'\'.*?\'\'\')\n', re.DOTALL)


def strip_prefix(prefix: str, text: str) -> str:
    """Quita el bloque de imports del proyecto de un módulo.

    Los ficheros exportados llevan ese bloque dentro del bloque de imports;
    al sembrar el cuaderno no debe aparecer, porque allí los nombres ya están
    definidos por las celdas anteriores.
    """
    if not prefix:
        return text
    while prefix in text:
        text = text.replace(prefix, "", 1)
    # normalizar las líneas en blanco que dejó el bloque retirado
    while "\n\n\n\n" in text:
        text = text.replace("\n\n\n\n", "\n\n\n")
    return text


BASE = ROOT / "tools" / "notebook_base.ipynb"
NOTEBOOK = ROOT / "MiniTcl_Analizador_Descendente_Recursivo_Guia_Estudiante.ipynb"


def make_id() -> str:
    """Identificador único de celda (lo exige nbformat 4.5+)."""
    return uuid.uuid4().hex[:8]


# Qué celdas se insertan después de cada encabezado del cuaderno.
ANCHORS = [
    ("## 8. Modelo del AST", [("model", "model.py", 1)]),
    ("## 9. Infraestructura mínima", [("model", "model.py", 2), ("model", "script_lexer.py", 1)]),
    (
        "## 10. Esqueleto del parser",
        [
            ("model", "script_parser.py", 1),
            ("model", "list_reader.py", 1),
            ("model", "expr_lexer.py", 1),
        ],
    ),
    (
        "## 12. Esqueleto mínimo de expresiones",
        [
            ("notebook", "pip", 0),
            ("model", "expr_parser.py", 1),
            ("model", "command_analyzer.py", 1),
        ],
    ),
]

# Las celdas de las fachadas, la demostración del pipeline y la suite de
# pruebas van detrás de las pruebas del material suministrado.  La demostración
# va después de las fachadas porque necesita las dos: parse_minitcl (rama de
# scripts) y parse_minitcl_expr (rama de expresiones).
AFTER_SUPPLIED_TESTS = [
    ("notebook", "facades", 0),
    ("model", "demo.py", 1),
    ("model", "tests/test_minitcl.py", 1),
]


def read_module_parts(name: str) -> list[str]:
    """Divide un módulo en las partes que corresponden a sus celdas.

    Hay dos modos de corte:

    * ``split`` (por defecto): el corte separa dos partes del módulo y el
      prefijo (imports del proyecto) va delante de todo.
    * ``prefix``: lo que precede al corte es el prefijo del módulo y lo que
      sigue es su única parte (así ocurre con el fichero de pruebas, cuyo
      preámbulo con los imports no debe aparecer en la celda del cuaderno).
    """
    text = strip_prefix(MODULES[name]["prefix"], (ROOT / name).read_text(encoding="utf-8"))
    suffix = MODULES[name].get("suffix", "")
    if suffix:
        text = text.replace(suffix, "")
    cuts = CUTS.get(name, [])
    if not cuts:
        return [text]
    if MODULES[name].get("cut_mode") == "prefix":
        return [text[text.index(cuts[0]):]]
    parts = []
    rest = text
    for cut in cuts:
        index = rest.index(cut)
        parts.append(rest[:index])
        rest = rest[index:]
    parts.append(rest)
    return parts


def module_cell_source(name: str, index: int, total: int) -> str:
    """Código de una celda, con la marca que la relaciona con su módulo."""
    parts = read_module_parts(name)
    marker = f"# === MODULE: {name} | PARTE {index}/{total} ==="
    return marker + "\n" + parts[index - 1]


def code_cell(source: str, identifier: str = ""):
    return {
        "cell_type": "code",
        "id": identifier or make_id(),
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


def markdown_cell(source: str, identifier: str = ""):
    return {
        "cell_type": "markdown",
        "id": identifier or make_id(),
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }


FACADES_SOURCE = '''# --- Las dos fachadas públicas ------------------------------------------------
#
#   parse_minitcl(source)            -> script_parser.py
#       Lexer manual + ScriptParser descendente recursivo.  Devuelve un Script.
#   parse_minitcl_expr(source, ...)  -> expr_parser.py
#       ExprLexer(sly.Lexer) + ExprParser(sly.Parser).  Devuelve un Expr.
#
# Ninguna de las dos ejecuta el programa: sólo construyen el AST.  Ambas lanzan
# ParseError ante una entrada incorrecta.

RUN_STUDENT_TESTS = True  # Activar cuando estén listas las dos fachadas.
if RUN_STUDENT_TESTS:
    script = parse_minitcl('puts "Hola $nombre"; set x {a b}')
    assert len(script.commands) == 2
    assert len(script.commands[0].words) == 2
    greeting = script.commands[0].words[1]
    assert greeting.mode == "quoted"
    assert [type(p).__name__ for p in greeting.parts] == ["Literal", "Variable"]
    block = script.commands[1].words[2]
    assert block.mode == "braced" and block.parts[0].text == "a b"
    assert expr_shape(parse_minitcl_expr("2 + 3 * 4")) == ("+", 2, ("*", 3, 4))
    assert expr_shape(parse_minitcl_expr("10 - 3 - 2")) == ("-", ("-", 10, 3), 2)
    assert expr_shape(parse_minitcl_expr("2 ** 3 ** 2")) == ("**", 2, ("**", 3, 2))
    assert expr_shape(parse_minitcl_expr("-2 ** 2")) == ("-", ("**", 2, 2))
    assert expr_shape(parse_minitcl_expr("2 ** -3")) == ("**", 2, ("-", 3))
    print("Pruebas del estudiante: correctas.")
else:
    print("Pruebas completas pendientes: habilitar RUN_STUDENT_TESTS al terminar.")
'''

PIP_SOURCE = '''# SLY es necesario para la parte de expresiones.  Si el entorno no lo tiene,
# ejecute "%pip install sly" en una celda aparte y reinicie el kernel.
try:
    import sly
    print("sly disponible:", getattr(sly, "__version__", "instalado"))
except ImportError:  # pragma: no cover - depende del entorno
    print("SLY no está instalado: las celdas de expresiones no podrán ejecutarse.")
'''


SUMMARY = """## 21. Entrega: módulos, pruebas y respuestas

El cuaderno es la fuente de verdad de la entrega.  Cada celda de código lleva la marca `# === MODULE: <fichero> | PARTE n/m ===`; `tools/export_modules.py` reconstruye los módulos a partir del cuaderno, de modo que **cuaderno y módulos no pueden divergir**.

| Módulo | Contenido |
|---|---|
| `model.py` | AST (`Span`, `Node`, `Word`, `Script`, `Expr`…), `Token`, `ParseError` con línea y columna, `cover()`, `expr_shape()` y el `TokenCursor`. |
| `script_lexer.py` | Lexer manual contextual: modos comando/llaves/comillas, escapes, variables, balanceo, comentarios y `scan_substitution()`. |
| `script_parser.py` | `ScriptParser` descendente recursivo, `parse_minitcl()` y el callback `read_substitution()`. |
| `list_reader.py` | Lector de listas (`LIST_WS`, `LIST_BRACED`, `LIST_QUOTED`, `LIST_BARE`) y `format_list()`. |
| `expr_lexer.py` | `ExprLexer(sly.Lexer)` con los tokens de la sección 5 y la regla `CMD_SUBST` que delega en el lexer manual. |
| `expr_parser.py` | `ExprParser(sly.Parser)` con la gramática por niveles y `parse_minitcl_expr()`. |
| `command_analyzer.py` | Validación de las formas de comando y reanálisis estático de cuerpos y condiciones. |
| `tests/test_minitcl.py` | Pruebas reproducibles (no requieren `pytest`). |
| `demo.py` | Demostración en la terminal: `python3 demo.py tokens/ast/formas/expr/archivo/pruebas`. |
| `ejemplos/` | Los cuatro programas de aceptación de la sección 15 y uno con un error. |
| `Makefile` | El ciclo de trabajo: `make test`, `make demo`, `make build`, `make run`, `make check`. |

Ciclo de trabajo (`make help` lista todos los objetivos):

```bash
make test                                  # las 35 pruebas
make demo                                  # la demostración en la terminal
make build                                 # regenera el cuaderno y los módulos
make run                                   # ejecuta el cuaderno y guarda las impresiones
make check                                 # build + test + run (el ciclo completo)
```

`make build` va siempre **antes** que `make run`: regenerar el cuaderno borra las impresiones que había guardado.

Comandos de análisis (el texto va entre comillas; si se omite, el programa lo pide por la entrada estándar):

```bash
make tokens TEXTO="set x 1"                   # tokens del lexer manual
make ast    TEXTO="set x 1"                   # AST del parser descendente recursivo
make formas TEXTO="if {1} {puts si}"          # formas de comando detectadas
make expr   EXPR="2 + 3 * 4"                 # tokens + AST de una expresión (SLY)
make archivo FILE=ejemplos/a_factorial.tcl    # fichero MiniTcl: tokens + AST + formas
```

Los mismos comandos sin `make`, que además aceptan ficheros y las pruebas:

```bash
python3 demo.py tokens "set x 1"
python3 demo.py ast "set x 1"
python3 demo.py formas "if {1} {puts si}"
python3 demo.py expr "2 + 3 * 4"
python3 demo.py archivo ejemplos/a_factorial.tcl
python3 demo.py pruebas
python3 demo.py ayuda
```
"""

ANSWERS = [
    """### 21.1  Actividad de la sección 11: por qué el modo del lexer es parte del contrato

El significado de un carácter **depende del contexto**, así que el modo no es un detalle de implementación del lexer sino parte del contrato léxico:

| Contexto | `{` | `}` | `"` | `$` | `[` | `]` | `#` | `;` |
|---|---|---|---|---|---|---|---|---|
| palabra desnuda | error | error | error | abre variable | abre sustitución | termina la palabra | texto | separador |
| entre llaves | texto | texto | texto | texto | texto | texto | texto | texto |
| entre comillas | texto | texto | cierra | abre variable | abre sustitución | texto | texto | texto |
| inicio de palabra | abre bloque | — | abre palabra | abre variable | abre sustitución | error fuera de contexto | comentario si empieza un comando | separador |

Una expresión regular aislada (o una lista plana de tokens) **no** puede expresar esa tabla: el valor de `#` depende de si la posición permite empezar un comando, y el de `}` depende del balanceo de llaves.  Por eso el lexer mantiene una pila de marcos (`command` / `quote`) y por eso el parser descendente recibe `BRACED`, `QOPEN` y `QCLOSE` como tokens ya decididos: nunca vuelve a examinar su contenido.

No se afirma que toda la sintaxis de Tcl sea una gramática LL(1) sobre caracteres: el análisis léxico es contextual (con pila de modos) y sólo después de tokenizar, la gramática estructural es LL(1) sobre esos tokens.
""",
    """### 21.2  Actividad de la sección 12: recursividad izquierda y AST

**Asociación a la izquierda.**  `additive : additive MINUS multiplicative` es recursiva por la izquierda: el parser resuelve `10 - 3` y, antes de reducir `additive`, ve que el siguiente token es `-`; entonces desplaza el `additive` ya leído a la izquierda y continúa.  La reducción sólo ocurre cuando la mirada no es `+` ni `-`, de modo que `10 - 3 - 2` se agrupa como `(10 - 3) - 2`.

**Asociación a la derecha.**  `power : primary POWER unary` es recursiva por la derecha: el operando derecho se analiza como un `unary` completo, que puede ser a su vez otro `power`; así `2 ** 3 ** 2` se agrupa como `2 ** (3 ** 2)`.

**Precedencia entre unario y potencia.**  `unary : MINUS unary | power` y `power : primary POWER unary | primary`.  El token `**` sólo puede seguir a un `primary`, de modo que en `-2 ** 2` el `**` se une al `primary` antes de que el `unary` se reduzca: `-(2 ** 2)`.  En `2 ** -3` el `**` ya está consumido y el operando derecho es `unary -> MINUS unary`: `2 ** (-3)`.

Los AST que se pedían dibujar antes de evaluarlos:

```
8 / 2 * 3         ->  Binary('*', Binary('/', 8, 2), 3)
2 ** 3 ** 2       ->  Binary('**', 2, Binary('**', 3, 2))
-(4 + 1)          ->  Unary('-', Binary('+', 4, 1))
$a(3) + [doble 2] ->  Binary('+', VariableExpr(Variable('a', '3')),
                              SubstitutionExpr(Script(...)))
```

Los paréntesis de agrupación no crean nodo propio: su contenido se devuelve tal cual.
""",
    """### 21.3  Actividad de la sección 13: `analyze_command`

La segunda pasada vive en `command_analyzer.py` y **no sustituye** al AST estructural: lo anota.

```python
@dataclass(frozen=True)
class ArgumentAnalysis:
    word_index: int          # índice de la palabra dentro del comando
    kind: str                # 'expr' | 'script' | 'list' | 'name' |
                              # 'identifier' | 'word'
    span: Span
    value: object = None     # Expr, Script, tuple[str] o Word

@dataclass(frozen=True)
class CommandAnalysis:
    command: Command         # el comando estructural, intacto
    form: str                # 'set_cmd', 'if_cmd', 'call_cmd', ...
    arguments: tuple[ArgumentAnalysis, ...]
    substitutions: tuple[ScriptAnalysis, ...]   # los [ ... ] del comando
    bodies: tuple[ScriptAnalysis, ...]          # los cuerpos reanalizados
```

`analyze_command(command, source, source_name)` devuelve un `CommandAnalysis`; `analyze_script(script, ...)` devuelve un `ScriptAnalysis` con el análisis de cada comando, y `analyze_minitcl(source)` es la fachada que analiza y valida.

Reglas que aplica:

* La **forma** se comprueba contra la tabla de la sección 6 (aridad y estructura).  `call_cmd` es la forma general y no se prueba después de fallar con un incorporado.
* El **nombre** del comando debe ser literal; un nombre calculado (`$accion hola`) es estructuralmente válido pero el validador lo rechaza como fuera del perfil.
* Las **condiciones** (`expr`, `if`, `elseif`, `while`, `for`) se entregan a `parse_minitcl_expr`; los **cuerpos** de `if`, `elseif`, `while`, `for`, `foreach`, `proc` y `catch` se entregan a `parse_minitcl`.  Los dos caminos comparten la misma fachada de expresiones: no existe un segundo parser de condiciones.
* Al reanalizar un `BRACED`, la posición interior es `word.span.start + 1`; ese desplazamiento se propaga a los spans y al nombre de la fuente, de modo que las posiciones no se calculan sobre texto interpolado.
* Los bloques de `set`, `puts`, `list` o los datos de `dict` **no** se interpretan como scripts.
* Los corchetes ya producen un `Script` durante el análisis estructural: el validador los visita también.
* Un error de sintaxis dentro de un cuerpo estático se reporta aunque la rama no se tome: el cuerpo se analiza y se valida siempre.
""",
    """### 21.4  Actividad de la sección 15: invocaciones recursivas de análisis

Se analiza el programa A:

```tcl
proc factorial {n} {
    if {$n <= 1} {return 1}
    return [expr {$n * [factorial [expr {$n - 1}]]}]
}
puts [factorial 6]
```

Invocaciones de análisis, en orden:

1. `parse_minitcl(programa)` — el script completo.
2. El comando `proc`: su **cuerpo** `BRACED` se reanaliza con `parse_minitcl` (base `+1`), y dentro de ese cuerpo:
3. El comando `if`: su **condición** `{$n <= 1}` se entrega a `parse_minitcl_expr` y su **cuerpo** `{return 1}` a `parse_minitcl`.
4. El comando `return`: su argumento `[expr {...}]` ya es un `Script` construido por el parser manual; el validador lo visita y dentro aparece el comando `expr`, cuyo argumento `{$n * [factorial [expr {$n - 1}]]}` se entrega a `parse_minitcl_expr`.
5. Esa expresión contiene otra sustitución: el lexer de SLY llama a `read_substitution`, que vuelve al **parser manual** y produce el `Script` del comando `factorial`; su argumento `[expr {$n - 1}]` es otra sustitución, y su expresión `{$n - 1}` se entrega de nuevo a `parse_minitcl_expr`.
6. El comando `puts`: su argumento `[factorial 6]` es un `Script` estructural que también se visita.

Las palabras cuyo contenido debe analizarse de nuevo son exactamente las **palabras `BRACED`** con un papel definido por la forma del comando: el cuerpo de `proc`, la condición y el cuerpo de `if`, y el argumento de cada `expr` (incluidos los que aparecen dentro de una sustitución).  Las palabras `puts`, `proc`, `factorial`, `return` e `if` son nombres literales de comando y no se reanalizan; `n` es una variable de la expresión y se resuelve en tiempo de ejecución, no de análisis.
""",
    """### 21.5  Actividad de la sección 17: línea y columna

Los offsets del `Span` se refieren a la fuente **normalizada** (CRLF y CR convertidos a LF antes de lexear).  Para un offset `o`:

```python
line = source.count("\n", 0, o) + 1
line_start = source.rfind("\n", 0, o) + 1
column = o - line_start + 1
```

Eso es exactamente lo que hace `model.position_of`.  `model.format_diagnostic` compone el mensaje con fuente, línea y columna, y añade el fragmento afectado con un cursor (`^`) debajo.  `ParseError` guarda `line`, `column` y `span`, y el `TokenCursor` acepta la fuente y el desplazamiento base para que las posiciones sigan siendo correctas al reanálisis de un bloque interior (`base_offset = word.span.start + 1`).

Para un cierre faltante, el error del lexer se produce en la posición de **apertura** (`{`, `"` o `[`), que es donde el lector puede localizar el problema.
""",
    """### 21.6  Las ocho preguntas del cuaderno

**1. ¿Por qué `set x {$y}` no debe generar una referencia a `y`?**

Porque una palabra entre llaves es literal: el lexer cuenta las llaves anidadas y devuelve su contenido interior como un único `Literal`, sin interpretar `$`, `[` ni escapes.  Sólo las palabras desnudas y entre comillas contienen sustituciones.  El validador tampoco reanaliza el valor de `set`, porque la forma `set_cmd` no lo exige.

**2. ¿Qué evita que `hola_$nombre` se convierta en dos argumentos?**

El lexer emite el fragmento `TEXT` `hola_` y el token `VAR` `$nombre` **sin** ningún `WS` ni `SEP` entre ellos, y `parse_bare_word` acumula partes contiguas (`TEXT | VAR | LBRACKET`) en una sola `Word`.  Los límites de palabra sólo los crean los espacios en blanco y los separadores.

**3. ¿Qué parte del sistema distingue `set n 12` de `expr {12}`?**

La validación de comandos (segunda pasada).  Los dos son, para el parser estructural, un comando con dos palabras.  `set_cmd` exige un nombre literal y un valor que **no** se reanaliza; `expr_cmd` exige exactamente una palabra entre llaves, y su contenido se entrega a `parse_minitcl_expr`, que lo analiza con SLY.

**4. ¿Por qué la gramática de SLY admite recursividad izquierda para la suma, mientras la potencia asocia a la derecha?**

Porque está escrito así: `additive : additive PLUS multiplicative` deja el operando izquierdo ya construido y permite continuar con otro `+`/`-` antes de reducir (asociación izquierda), mientras que `power : primary POWER unary` construye primero el operando derecho como un `unary` completo, que puede ser otro `power` (asociación derecha).  El autómata LALR(1) que genera SLY admite ambas formas y los niveles de la gramática dan la precedencia sin tabla `precedence` adicional.

**5. ¿Cómo conserva el análisis de `0 && [error fallo]` la posibilidad de cortocircuito?**

Porque el análisis nunca evalúa.  La sustitución sólo se **analiza**: el lexer manual construye un `Script` y el parser de SLY lo envuelve en un `SubstitutionExpr`.  El AST queda como `Binary('&&', 0, SubstitutionExpr(...))` y la decisión de no evaluar el operando derecho cuando el izquierdo es falso queda en manos del evaluador futuro.  Ningún paso consulta el valor de `x` ni ejecuta el cuerpo de la sustitución.

**6. ¿Qué hace el lexer con `]` dentro de llaves y con `;` dentro de comillas?**

Dentro de las llaves, `]` es texto: el balanceo se cuenta con llaves, no con corchetes.  Dentro de las comillas, `;` forma parte del `TEXT` y no separa comandos; sólo `"` cierra la palabra entre comillas.  En cambio, un `]` en el nivel exterior es un error de cierre fuera de contexto.

**7. ¿Qué errores puede detectar el parser genérico y cuáles requieren conocer el comando?**

El parser genérico detecta los errores léxicos (llaves, comillas o corchetes sin cerrar, escapes desconocidos, `$` sin nombre, `]` fuera de contexto, texto tras una palabra agrupada) y los estructurales (falta un separador entre comandos, token inesperado al empezar una palabra, `]` que no cierra).  No puede detectar los errores de forma: `set x 1 2`, `if {1} {puts si} else` o `proc f {x x} {...}` son AST estructurales válidos y los rechaza la segunda pasada, que sí conoce el comando.

**8. ¿Cómo cambian los contextos de `break` y `return` al entrar a un nuevo procedimiento?**

`return` sólo es válido dentro de un procedimiento: al invocar uno se crea un ámbito local nuevo, y el contexto "estoy en un procedimiento" debe establecerse para el cuerpo.  `break` y `continue` requieren un ciclo **en el procedimiento actual** y no pueden escapar al ciclo del llamador, así que al entrar en un procedimiento el contexto de ciclos se reinicia (se guarda y se restaura).  En esta entrega sólo se analiza la forma sintáctica; el análisis estático de un cuerpo crea precisamente ese contexto nuevo, y por eso un `return` fuera de un procedimiento, o un `break` sin ciclo en el procedimiento actual, se detectan en la segunda pasada.
""",
]


def build_cells(base_cells):
    """Inserta las celdas generadas en el base, usando anclas semánticas."""
    result = []
    for cell in base_cells:
        cell = dict(cell)
        cell.setdefault("id", make_id())
        result.append(cell)
        source = "".join(cell["source"])
        for anchor, items in ANCHORS:
            if cell["cell_type"] != "markdown" or not source.startswith(anchor):
                continue
            for kind, name, index in items:
                result.extend(append_with_followers(build_cell(kind, name, index)))
        if source.startswith("# Pruebas del material suministrado"):
            for kind, name, index in AFTER_SUPPLIED_TESTS:
                result.extend(append_with_followers(build_cell(kind, name, index)))
    result.append(markdown_cell(SUMMARY))
    for answer in ANSWERS:
        result.append(markdown_cell(answer))
    return result


def build_cell(kind: str, name: str, index: int) -> dict:
    if kind == "notebook":
        source = {"pip": PIP_SOURCE, "facades": FACADES_SOURCE}[name]
        return code_cell(source)
    total = MODULES[name]["parts"]
    return code_cell(module_cell_source(name, index, total))


def append_with_followers(cell: dict) -> list[dict]:
    """Devuelve la celda y, si procede, las que deben ir detrás de ella."""
    return [cell]


def main() -> int:
    base = json.loads(BASE.read_text(encoding="utf-8"))
    notebook = dict(base)
    notebook["cells"] = build_cells(base["cells"])
    metadata = notebook.setdefault("metadata", {})
    validation = metadata.setdefault("minitcl_validation", {})
    validation.update(
        {
            "sly_version": "0.5",
            "expression_grammar_shift_reduce_conflicts": 0,
            "expression_grammar_reduce_reduce_conflicts": 0,
            "student_implementation_complete": True,
        }
    )
    NOTEBOOK.write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"Cuaderno actualizado: {NOTEBOOK.name} ({len(notebook['cells'])} celdas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
