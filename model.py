"""Modelo de datos de MiniTcl: AST, spans, tokens y diagnósticos.

Los nombres de código están en inglés y las explicaciones en español, según el
contrato de la sección 18 del cuaderno.

Los spans son intervalos semiabiertos ``[start, end)`` sobre la fuente
normalizada (CRLF/CR convertidos a LF antes de analizar).
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Literal as Mode


@dataclass(frozen=True)
class Span:
    """Posición semiabierta ``[start, end)`` dentro de una fuente."""

    start: int
    end: int
    source: str = "<input>"


@dataclass(frozen=True, kw_only=True)
class Node:
    span: Span


@dataclass(frozen=True)
class Literal(Node):
    text: str


@dataclass(frozen=True)
class Variable(Node):
    name: str
    index: str | None = None


@dataclass(frozen=True)
class CommandSubstitution(Node):
    script: Script


Part = Literal | Variable | CommandSubstitution


@dataclass(frozen=True)
class Word(Node):
    parts: tuple[Part, ...]
    mode: Mode["bare", "quoted", "braced"] = "bare"


@dataclass(frozen=True)
class Command(Node):
    words: tuple[Word, ...]


@dataclass(frozen=True)
class Script(Node):
    commands: tuple[Command, ...]


@dataclass(frozen=True, kw_only=True)
class Expr(Node):
    pass


@dataclass(frozen=True)
class Constant(Expr):
    value: int | float | str | bool


@dataclass(frozen=True)
class VariableExpr(Expr):
    variable: Variable


@dataclass(frozen=True)
class SubstitutionExpr(Expr):
    script: Script


@dataclass(frozen=True)
class Unary(Expr):
    operator: str
    operand: Expr


@dataclass(frozen=True)
class Binary(Expr):
    operator: str
    left: Expr
    right: Expr


def cover(first: Span, last: Span) -> Span:
    """Span que cubre dos spans del mismo documento.

    Es el helper que usa el esqueleto de ``ScriptParser`` y que el cuaderno
    nunca llegó a definir.
    """
    return Span(first.start, last.end, first.source)


def position_of(source_text: str | None, offset: int) -> tuple[int, int]:
    """Devuelve ``(linea, columna)`` con base 1 para un offset de la fuente."""
    if source_text is None:
        return 0, 0
    offset = max(0, min(offset, len(source_text)))
    line = source_text.count("\n", 0, offset) + 1
    line_start = source_text.rfind("\n", 0, offset) + 1
    return line, offset - line_start + 1


def source_line(source_text: str | None, line: int) -> str:
    """Devuelve el texto de la línea ``line`` (base 1) de la fuente."""
    if source_text is None:
        return ""
    lines = source_text.split("\n")
    if 1 <= line <= len(lines):
        return lines[line - 1]
    return ""


def format_diagnostic(
    message: str,
    span: Span,
    source_text: str | None = None,
    offset: int | None = None,
) -> str:
    """Compone el diagnóstico: fuente, línea, columna, fragmento y cursor."""
    position = span.start if offset is None else offset
    line, column = position_of(source_text, position)
    header = f"{span.source}:{line}:{column}: {message}"
    if source_text is None:
        return header
    text = source_line(source_text, line)
    if not text:
        return header
    caret = " " * max(0, column - 1) + "^"
    return f"{header}\n  {text}\n  {caret}"


@dataclass(frozen=True)
class Token:
    """Token del lexer manual de scripts.

    ``index`` guarda el índice literal de un arreglo (``$a(3)``) y es ``None``
    para el resto de tokens.
    """

    kind: str
    value: str
    span: Span
    index: str | None = None


class ParseError(Exception):
    """Error de análisis léxico o sintáctico con posición localizada."""

    def __init__(
        self,
        message: str,
        span: Span,
        source_text: str | None = None,
        offset: int | None = None,
    ):
        self.message = message
        self.span = span
        self.source_text = source_text
        self.offset = span.start if offset is None else offset
        self.line, self.column = position_of(source_text, self.offset)
        super().__init__(format_diagnostic(message, span, source_text, self.offset))


class TokenCursor:
    """Cursor sobre una secuencia de tokens terminada en ``EOF``."""

    def __init__(self, tokens, source: str | None = None, source_base_offset: int = 0):
        self.tokens = tuple(tokens)
        if not self.tokens or self.tokens[-1].kind != "EOF":
            raise ValueError("El lexer debe agregar EOF")
        self.position = 0
        self.source = source
        self.source_base_offset = source_base_offset

    @property
    def current(self):
        return self.tokens[self.position]

    def accept(self, kind):
        if self.current.kind != kind:
            return None
        token = self.current
        if kind != "EOF":
            self.position += 1
        return token

    def expect(self, kind):
        token = self.accept(kind)
        if token is None:
            self.fail(f"Se esperaba {kind}; se encontró {self.current.kind}", self.current.span)
        return token

    def skip(self, *kinds):
        while self.current.kind in kinds and self.current.kind != "EOF":
            self.position += 1

    def fail(self, message: str, span: Span) -> None:
        """Lanza un ``ParseError`` con línea y columna calculadas."""
        offset = span.start - self.source_base_offset
        raise ParseError(message, span, self.source, offset)


# --- Vistas del AST ---------------------------------------------------------
# La impresión del cuaderno (show_ast) recorre los campos del dataclass y por
# eso ocupa una línea por campo.  Estas funciones dan la misma información en
# una línea por nodo, que es lo que se lee de un vistazo en la terminal.


def _parte_etiqueta(parte: "Part") -> str:
    """Etiqueta corta de una parte de palabra."""
    if isinstance(parte, Literal):
        return repr(parte.text)
    if isinstance(parte, Variable):
        return f"${parte.name}" + (f"({parte.index})" if parte.index else "")
    return "[...]"


def _etiqueta_y_hijos(valor) -> tuple[str, list]:
    """Etiqueta de un nodo del AST y la lista de sus hijos."""
    if isinstance(valor, Script):
        return f"Script ({len(valor.commands)} comandos)", list(valor.commands)
    if isinstance(valor, Command):
        return f"Command ({len(valor.words)} palabras)", list(valor.words)
    if isinstance(valor, Word):
        partes = " + ".join(_parte_etiqueta(parte) for parte in valor.parts)
        return f"Word({valor.mode}) {partes}", []
    if isinstance(valor, Literal):
        return f"Literal {valor.text!r}", []
    if isinstance(valor, Variable):
        return f"Variable ${valor.name}" + (f"({valor.index})" if valor.index else ""), []
    if isinstance(valor, CommandSubstitution):
        return "CommandSubstitution [...]", [valor.script]
    if isinstance(valor, Constant):
        return f"Constant {valor.value!r}", []
    if isinstance(valor, VariableExpr):
        return f"VariableExpr ${valor.variable.name}", []
    if isinstance(valor, SubstitutionExpr):
        return "SubstitutionExpr [...]", [valor.script]
    if isinstance(valor, Unary):
        return f"Unary({valor.operator})", [valor.operand]
    if isinstance(valor, Binary):
        return f"Binary({valor.operator})", [valor.left, valor.right]
    return repr(valor), []


def ast_lines(valor, sangria: int = 0, ultimo: bool = True, raiz: bool = False) -> list[str]:
    """El AST como árbol de una línea por nodo."""
    etiqueta, hijos = _etiqueta_y_hijos(valor)
    if raiz:
        cabecera = etiqueta
    else:
        cabecera = ("└─ " if ultimo else "├─ ") + etiqueta
    lineas = [" " * sangria + cabecera]
    siguiente = sangria if raiz else sangria + 3
    for indice, hijo in enumerate(hijos):
        lineas += ast_lines(hijo, siguiente, indice == len(hijos) - 1)
    return lineas


def show_ast_compact(valor) -> None:
    """Imprime el AST como árbol compacto (una línea por nodo)."""
    for linea in ast_lines(valor, raiz=True):
        print(linea)


def expr_shape(node):
    """Proyección del AST de expresiones para comparar forma sin offsets."""
    if isinstance(node, Constant):
        return node.value
    if isinstance(node, Unary):
        return (node.operator, expr_shape(node.operand))
    if isinstance(node, Binary):
        return (node.operator, expr_shape(node.left), expr_shape(node.right))
    if isinstance(node, VariableExpr):
        return ("var", node.variable.name, node.variable.index)
    if isinstance(node, SubstitutionExpr):
        return ("subst", tuple(len(c.words) for c in node.script.commands))
    raise TypeError(type(node).__name__)
