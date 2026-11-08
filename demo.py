"""Demostración del pipeline de análisis sintáctico de MiniTcl.

Sin argumentos muestra las dos ramas del analizador:

    Rama de scripts :  fuente --(lexer manual)--> tokens --(parser descendente)--> AST
    Rama de expr    :  texto  --(sly.Lexer)--> tokens --(sly.Parser LALR)--> AST

Con un argumento analiza ese fichero MiniTcl:

    python3 demo.py ejemplos/a_factorial.tcl

Los tokens son el resultado del análisis léxico y el AST el del análisis
sintáctico.  Ninguna de las dos etapas ejecuta el programa.
"""

from dataclasses import fields, is_dataclass

from command_analyzer import analyze_minitcl
from expr_lexer import ExprLexer
from expr_parser import parse_minitcl_expr
from model import ParseError
from script_lexer import show_tokens, tokenize_script
from script_parser import parse_minitcl, read_substitution


def show_ast(value, indent=0):
    """Impresión estructurada del AST, sin Graphviz ni dependencias externas."""
    prefix = " " * indent
    if is_dataclass(value):
        print(prefix + type(value).__name__)
        for field in fields(value):
            if field.name == "span":
                continue
            print(prefix + "  " + field.name + ":")
            show_ast(getattr(value, field.name), indent + 4)
    elif isinstance(value, tuple):
        for item in value:
            show_ast(item, indent)
    else:
        print(prefix + repr(value))



# --- El cuerpo del módulo empieza aquí (se convierte en la celda del cuaderno).
import sys  # el cuerpo se genera desde el cuaderno, por eso el import va aquí


def argumentos_de_cli() -> list:
    """Argumentos de la línea de órdenes (vacíos dentro del cuaderno)."""
    if "get_ipython" in globals():
        return []
    return sys.argv[1:]


def demostrar_script(fuente: str, nombre: str = "<input>") -> None:
    """Tokens y AST de un script MiniTcl."""
    print(f"=== Script {nombre} -> lexer manual -> tokens -> parser descendente -> AST ===")
    show_tokens(tokenize_script(fuente, nombre))
    print("  --- AST ---")
    show_ast(parse_minitcl(fuente, nombre))


def demostrar_expresion(expresion: str) -> None:
    """Tokens y AST de una expresión."""
    print(f"=== Expresion {expresion!r} -> sly.Lexer -> tokens -> sly.Parser (LALR) -> AST ===")
    # El lexer de SLY necesita el callback que lee la sustitución con el lexer
    # manual de scripts: ese es el puente entre las dos ramas del analizador.
    lexer = ExprLexer(read_substitution=read_substitution)
    show_tokens(list(lexer.tokenize(expresion)))
    print("  --- AST ---")
    show_ast(parse_minitcl_expr(expresion))


def demostrar_archivo(ruta: str) -> None:
    """Tokens, AST y formas de comando de un fichero MiniTcl."""
    with open(ruta, encoding="utf-8") as fichero:
        fuente = fichero.read()
    try:
        demostrar_script(fuente, ruta)
        print("  --- formas de comando ---")
        for comando in analyze_minitcl(fuente, ruta).commands:
            print(f"  {comando.form:16} {len(comando.command.words)} palabras")
    except ParseError as error:
        print()
        print("=== Diagnóstico ===")
        print(error)
        raise SystemExit(1)


_argumentos = argumentos_de_cli()
if _argumentos:
    demostrar_archivo(_argumentos[0])
else:
    demostrar_script("set x hola_${nombre}_fin")
    print()
    demostrar_expresion("$n * 2 + [doble 1]")
