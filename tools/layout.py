"""Correspondencia entre el cuaderno y los módulos entregables.

El cuaderno es la fuente de verdad: cada celda de código lleva una marca

    # === MODULE: <ruta del módulo> | PARTE <n>/<m> ===

y las partes de un mismo módulo se concatenan, en orden, para reconstruir el
fichero. El ``prefix`` es el texto que se antepone al módulo exportado: los
imports de los módulos del proyecto, que en el cuaderno no hacen falta porque
las celdas anteriores ya han definido esos nombres.
"""

from __future__ import annotations

MODULES = {
    "model.py": {
        "prefix": "",
        "parts": 2,
        "cell": 9,
    },
    "script_lexer.py": {
        "prefix": "from model import ParseError, Span, Token\n",
        "parts": 1,
        "cell": None,
    },
    "script_parser.py": {
        "prefix": (
            "from model import (\n"
            "    Command,\n"
            "    CommandSubstitution,\n"
            "    Literal,\n"
            "    Part,\n"
            "    ParseError,\n"
            "    Script,\n"
            "    Span,\n"
            "    Token,\n"
            "    TokenCursor,\n"
            "    Variable,\n"
            "    Word,\n"
            "    cover,\n"
            ")\n"
            "from script_lexer import scan_substitution, tokenize_script\n"
        ),
        "parts": 1,
        "cell": None,
    },
    "list_reader.py": {
        "prefix": "from model import ParseError, Span\n",
        "parts": 1,
        "cell": None,
    },
    "expr_lexer.py": {
        "prefix": "from model import ParseError, Span\n",
        "parts": 1,
        "cell": None,
    },
    "expr_parser.py": {
        "prefix": (
            "from expr_lexer import ExprLexer\n"
            "from model import (\n"
            "    Binary,\n"
            "    Constant,\n"
            "    Expr,\n"
            "    ParseError,\n"
            "    Script,\n"
            "    Span,\n"
            "    SubstitutionExpr,\n"
            "    Unary,\n"
            "    Variable,\n"
            "    VariableExpr,\n"
            ")\n"
            "from script_parser import read_substitution\n"
        ),
        "parts": 1,
        "cell": None,
    },
    "command_analyzer.py": {
        "prefix": (
            "from expr_parser import parse_minitcl_expr\n"
            "from list_reader import parse_list\n"
            "from model import (\n"
            "    Command,\n"
            "    Expr,\n"
            "    Literal,\n"
            "    ParseError,\n"
            "    Script,\n"
            "    Span,\n"
            "    Word,\n"
            ")\n"
            "from script_parser import parse_minitcl\n"
        ),
        "parts": 1,
        "cell": None,
    },
    "demo.py": {
        # El prefijo son los imports del proyecto y el impresor del AST;
        # el cuerpo es lo que se convierte en la celda del cuaderno.
        "prefix": '"""Demostración del pipeline de análisis sintáctico de MiniTcl.\n\nSin argumentos muestra las dos ramas del analizador:\n\n    Rama de scripts :  fuente --(lexer manual)--> tokens --(parser descendente)--> AST\n    Rama de expr    :  texto  --(sly.Lexer)--> tokens --(sly.Parser LALR)--> AST\n\nCon un argumento analiza ese fichero MiniTcl:\n\n    python3 demo.py ejemplos/a_factorial.tcl\n\nLos tokens son el resultado del análisis léxico y el AST el del análisis\nsintáctico.  Ninguna de las dos etapas ejecuta el programa.\n"""\n\nfrom dataclasses import fields, is_dataclass\n\nfrom command_analyzer import analyze_minitcl\nfrom expr_lexer import ExprLexer\nfrom expr_parser import parse_minitcl_expr\nfrom model import ParseError\nfrom script_lexer import show_tokens, tokenize_script\nfrom script_parser import parse_minitcl, read_substitution\n\n\ndef show_ast(value, indent=0):\n    """Impresión estructurada del AST, sin Graphviz ni dependencias externas."""\n    prefix = " " * indent\n    if is_dataclass(value):\n        print(prefix + type(value).__name__)\n        for field in fields(value):\n            if field.name == "span":\n                continue\n            print(prefix + "  " + field.name + ":")\n            show_ast(getattr(value, field.name), indent + 4)\n    elif isinstance(value, tuple):\n        for item in value:\n            show_ast(item, indent)\n    else:\n        print(prefix + repr(value))\n\n\n',
        "parts": 1,
        "cut_mode": "prefix",
        "cell": None,
    },
    "tests/test_minitcl.py": {
        # El preámbulo (docstring, imports y ajuste del path) es el prefijo:
        # en el cuaderno esas celdas no hacen falta.
        "prefix": '"""Pruebas reproducibles del analizador sintáctico de MiniTcl.\n\nEl fichero no necesita ``pytest``: basta con ejecutarlo\n(``python3 tests/test_minitcl.py``).  Las funciones ``test_*`` también se\npueden recoger con cualquier corredor de pruebas.\n\nSe cubren:\n\n* las comprobaciones del material suministrado (celda 26 del cuaderno),\n* el contrato léxico (sección 3),\n* la gramática estructural (sección 4) y la matriz de la sección 16,\n* la gramática de expresiones de SLY (sección 5),\n* la validación de comandos y el reanálisis estático (secciones 6 y 13),\n* el lector de listas (sección 7),\n* los programas de aceptación de la sección 15).\n"""\n\nfrom __future__ import annotations\n\nimport io\nimport sys\nfrom contextlib import redirect_stdout\nfrom pathlib import Path\n\nsys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n\nfrom command_analyzer import analyze_command, analyze_minitcl, analyze_script\nfrom expr_lexer import ExprLexer\nfrom expr_parser import ExprParser, parse_minitcl_expr\nfrom list_reader import format_list, parse_list\nfrom model import (\n    Binary,\n    Command,\n    CommandSubstitution,\n    Constant,\n    Literal,\n    ParseError,\n    Script,\n    Span,\n    SubstitutionExpr,\n    Token,\n    TokenCursor,\n    Unary,\n    Variable,\n    VariableExpr,\n    Word,\n    cover,\n    expr_shape,\n)\nfrom script_lexer import show_tokens, tokenize_script\nfrom script_parser import ScriptParser, parse_minitcl, read_substitution\n\n\n\n',
        "parts": 1,
        "cut_mode": "prefix",
        "suffix": (
            "\n\nif __name__ == \"__main__\":\n"
            "    raise SystemExit(main())\n"
        ),
        "cell": None,
    },
}

# Marcas que se 인식en en el interior de un módulo para separar sus partes.
PART_MARKER = "# === MODULE: {name} | PARTE {index}/{total} ==="

# Separador que se usa para cortar un módulo en varias partes al sembrar el
# cuaderno.  Es una línea de comentario real del fichero, de modo que el
# módulo exportado es idéntico al sembrado.
CUTS = {
    "model.py": ["@dataclass(frozen=True)\nclass Token:"],
    "tests/test_minitcl.py": ["# --- Utilidades ---"],
    "demo.py": ["# --- El cuerpo del módulo empieza aquí"],
}
