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
from pathlib import Path  # idem

AYUDA = """MiniTcl · analizador sintáctico — comandos de la demostración

  python3 demo.py                              demostración por defecto (las dos ramas)
  python3 demo.py tokens   <texto>             tokens del lexer manual
  python3 demo.py ast      <texto>             AST del parser descendente recursivo
  python3 demo.py formas   <texto>             formas de comando detectadas
  python3 demo.py expr     <expresión>         tokens + AST de una expresión (SLY)
  python3 demo.py archivo  <fichero.tcl>       tokens + AST + formas de un fichero
  python3 demo.py <fichero.tcl>                atajo de "archivo"
  python3 demo.py pruebas                      corre las 35 pruebas automáticas
  python3 demo.py ayuda                        esta ayuda

  <texto> también se puede escribir a mano:  python3 demo.py ast
  (entonces el programa pide el texto por la entrada estándar)

En el Makefile hay atajos:  make tokens TEXTO="..."   make ast TEXTO="..."
"""


def argumentos_de_cli() -> list:
    """Argumentos de la línea de órdenes (vacíos dentro del cuaderno)."""
    if "get_ipython" in globals():
        return []
    return sys.argv[1:]


def leer_texto(por_prompt: bool) -> str:
    """El texto viene en la línea de órdenes o se pide por la entrada estándar."""
    if not por_prompt:
        return ""
    print("Escribe el programa MiniTcl (termina con una línea vacía):")
    lineas = []
    while True:
        try:
            linea = input()
        except EOFError:
            break
        if not linea.strip():
            break
        lineas.append(linea)
    return "\n".join(lineas)


def mostrar_tokens(fuente: str, nombre: str = "<terminal>") -> None:
    """Tokens del lexer manual de scripts."""
    print(f"--- tokens (lexer manual) de {nombre} ---")
    show_tokens(tokenize_script(fuente, nombre))


def mostrar_ast_script(fuente: str, nombre: str = "<terminal>") -> None:
    """AST del parser descendente recursivo."""
    print(f"--- AST (parser descendente recursivo) de {nombre} ---")
    show_ast(parse_minitcl(fuente, nombre))


def mostrar_formas(fuente: str, nombre: str = "<terminal>") -> None:
    """Formas de comando que valida la segunda pasada."""
    print(f"--- formas de comando de {nombre} ---")
    for comando in analyze_minitcl(fuente, nombre).commands:
        print(f"  {comando.form:16} {len(comando.command.words)} palabras")


def mostrar_expresion(expresion: str) -> None:
    """Tokens y AST de una expresión, con SLY."""
    print(f"--- tokens (sly.Lexer) de {expresion!r} ---")
    # El lexer de SLY necesita el callback que lee la sustitución con el lexer
    # manual de scripts: ese es el puente entre las dos ramas del analizador.
    lexer = ExprLexer(read_substitution=read_substitution)
    show_tokens(list(lexer.tokenize(expresion)))
    print(f"--- AST (sly.Parser, LALR) de {expresion!r} ---")
    show_ast(parse_minitcl_expr(expresion))


def demostrar_script(fuente: str, nombre: str = "<input>") -> None:
    """Tokens y AST de un script MiniTcl."""
    mostrar_tokens(fuente, nombre)
    mostrar_ast_script(fuente, nombre)


def demostrar_expresion(expresion: str) -> None:
    """Tokens y AST de una expresión."""
    mostrar_expresion(expresion)


def demostrar_archivo(ruta: str) -> int:
    """Tokens, AST y formas de comando de un fichero MiniTcl."""
    with open(ruta, encoding="utf-8") as fichero:
        fuente = fichero.read()
    try:
        demostrar_script(fuente, ruta)
        mostrar_formas(fuente, ruta)
    except ParseError as error:
        print()
        print("=== Diagnóstico ===")
        print(error)
        return 1
    return 0


def correr_pruebas() -> int:
    """Ejecuta la suite de pruebas del proyecto."""
    import subprocess

    guion = Path(__file__).resolve().parent / "tests" / "test_minitcl.py"
    return subprocess.run([sys.executable, str(guion)]).returncode


def principal(argumentos: list) -> int:
    """Punto de entrada de la demostración."""
    if not argumentos:
        demostrar_script("set x hola_${nombre}_fin")
        print()
        demostrar_expresion("$n * 2 + [doble 1]")
        return 0

    comando = argumentos[0]
    resto = argumentos[1:]

    if comando in ("ayuda", "help", "--help", "-h"):
        print(AYUDA)
        return 0
    if comando in ("pruebas", "tests"):
        return correr_pruebas()
    if comando in ("tokens", "ast", "formas"):
        texto = " ".join(resto) if resto else leer_texto(True)
        if not texto:
            print("No hay nada que analizar.")
            return 1
        try:
            if comando == "tokens":
                mostrar_tokens(texto)
            elif comando == "ast":
                mostrar_ast_script(texto)
            else:
                mostrar_formas(texto)
        except ParseError as error:
            print()
            print("=== Diagnóstico ===")
            print(error)
            return 1
        return 0
    if comando in ("expr", "expresion"):
        expresion = " ".join(resto) if resto else leer_texto(True)
        if not expresion:
            print("No hay nada que analizar.")
            return 1
        try:
            mostrar_expresion(expresion)
        except ParseError as error:
            print()
            print("=== Diagnóstico ===")
            print(error)
            return 1
        return 0
    if comando in ("archivo", "file"):
        if not resto:
            print("Falta el nombre del fichero.")
            return 1
        return demostrar_archivo(resto[0])
    # Si no es un comando conocido, se interpreta como la ruta de un fichero.
    return demostrar_archivo(comando)


_codigo = principal(argumentos_de_cli())
if _codigo and "get_ipython" not in globals():
    raise SystemExit(_codigo)
