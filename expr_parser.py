"""Parser LALR(1) de expresiones MiniTcl sobre ``sly.Parser``.

La gramática es la de la sección 5 del cuaderno: una gramática por niveles con
recursividad izquierda para los operadores asociativos a la izquierda. Los
niveles ya definen precedencia y asociatividad, así que no hace falta una
tabla ``precedence`` adicional. La tabla LALR(1) se genera sin conflictos
shift/reduce ni reduce/reduce.

Los identificadores de código están en inglés y los comentarios en español.
"""



from __future__ import annotations

from sly import Parser

from expr_lexer import ExprLexer
from model import (
    Binary,
    Constant,
    Expr,
    ParseError,
    Script,
    Span,
    SubstitutionExpr,
    Unary,
    Variable,
    VariableExpr,
)
from script_parser import read_substitution

TRUE_WORDS = {"true", "yes", "on"}
FALSE_WORDS = {"false", "no", "off"}

# Símbolos no terminales de la gramática de la sección 5. Se listan porque
# ``sly`` reutiliza el atributo ``tokens`` del parser para el iterador de
# tokens durante el análisis, y no puede usarse para distinguir un terminal.
NONTERMINALS = frozenset(
    {
        "expression",
        "logical_or",
        "logical_and",
        "equality",
        "relational",
        "additive",
        "multiplicative",
        "unary",
        "power",
        "primary",
    }
)


def number_value(raw: str) -> int | float:
    """Convierte el texto de un ``NUMBER`` a ``int`` o ``float``."""
    return float(raw) if any(char in raw for char in ".eE") else int(raw)


def bool_value(raw: str) -> bool:
    """Convierte una palabra booleana de MiniTcl a ``bool``."""
    return raw.lower() in TRUE_WORDS


class ExprParser(Parser):
    """Analizador sintáctico LALR(1) de expresiones."""

    tokens = ExprLexer.tokens
    start = "expression"

    def __init__(
        self,
        text: str = "",
        base_offset: int = 0,
        source_name: str = "<expr>",
        diagnostic_source: str | None = None,
        diagnostic_offset: int | None = None,
    ):
        self.text = text
        self.base_offset = base_offset
        self.source_name = source_name
        # La fuente de diagnóstico puede ser el fichero completo: así las
        # posiciones absolutas siguen siendo correctas al reanálisis.
        self.diagnostic_source = diagnostic_source if diagnostic_source is not None else text
        self.diagnostic_offset = base_offset if diagnostic_offset is None else diagnostic_offset

    # --- Utilidades ---------------------------------------------------------
    def span_of(self, p) -> Span:
        """Span que cubre la producción completa, desplazada por ``base_offset``."""
        return Span(
            self.base_offset + p.index,
            self.base_offset + p.end,
            self.source_name,
        )

    def operator_of(self, p) -> str:
        """Texto del token operador de una producción binaria o unaria.

        ``sly`` 0.5 no expone ``p.slice`` (eso es de PLY): la referencia al
        símbolo se toma de la lista interna de la producción. El operador es el
        único símbolo *terminal* de la producción; en las binarias ocupa la
        segunda posición y en las unarias la primera.
        """
        for symbol in p._slice:
            if symbol.type not in NONTERMINALS:
                return symbol.value
        raise AssertionError("la producción no contiene ningún token operador")

    def fail(self, message: str, start: int, end: int | None = None) -> None:
        if end is None:
            end = start + 1
        span = Span(start, end, self.source_name)
        offset = self.diagnostic_offset + (start - self.base_offset)
        raise ParseError(message, span, self.diagnostic_source, offset)

    # --- Gramática por niveles ---------------------------------------------
    @_("logical_or")
    def expression(self, p):
        return p.logical_or

    @_("logical_or OR logical_and", "logical_and")
    def logical_or(self, p):
        if len(p) == 1:
            return p.logical_and
        return Binary(
            operator=self.operator_of(p),
            left=p.logical_or,
            right=p.logical_and,
            span=self.span_of(p),
        )

    @_("logical_and AND equality", "equality")
    def logical_and(self, p):
        if len(p) == 1:
            return p.equality
        return Binary(
            operator=self.operator_of(p),
            left=p.logical_and,
            right=p.equality,
            span=self.span_of(p),
        )

    @_(
        "equality EQ relational",
        "equality NE relational",
        "equality STREQ relational",
        "equality STRNE relational",
        "relational",
    )
    def equality(self, p):
        if len(p) == 1:
            return p.relational
        return Binary(
            operator=self.operator_of(p),
            left=p.equality,
            right=p.relational,
            span=self.span_of(p),
        )

    @_(
        "relational LT additive",
        "relational LE additive",
        "relational GT additive",
        "relational GE additive",
        "additive",
    )
    def relational(self, p):
        if len(p) == 1:
            return p.additive
        return Binary(
            operator=self.operator_of(p),
            left=p.relational,
            right=p.additive,
            span=self.span_of(p),
        )

    @_("additive PLUS multiplicative", "additive MINUS multiplicative", "multiplicative")
    def additive(self, p):
        if len(p) == 1:
            return p.multiplicative
        return Binary(
            operator=self.operator_of(p),
            left=p.additive,
            right=p.multiplicative,
            span=self.span_of(p),
        )

    @_(
        "multiplicative TIMES unary",
        "multiplicative DIVIDE unary",
        "multiplicative MOD unary",
        "unary",
    )
    def multiplicative(self, p):
        if len(p) == 1:
            return p.unary
        return Binary(
            operator=self.operator_of(p),
            left=p.multiplicative,
            right=p.unary,
            span=self.span_of(p),
        )

    @_("PLUS unary", "MINUS unary", "NOT unary", "power")
    def unary(self, p):
        if len(p) == 1:
            return p.power
        return Unary(operator=self.operator_of(p), operand=p.unary, span=self.span_of(p))

    @_("primary POWER unary", "primary")
    def power(self, p):
        if len(p) == 1:
            return p.primary
        return Binary(
            operator=self.operator_of(p),
            left=p.primary,
            right=p.unary,
            span=self.span_of(p),
        )

    @_(
        "NUMBER",
        "BOOL",
        "VAR",
        "STRING",
        "LPAREN expression RPAREN",
        "CMD_SUBST",
    )
    def primary(self, p):
        if len(p) == 3:
            # Los paréntesis de agrupación no necesitan nodo propio.
            return p.expression
        symbol = p._slice[0]
        span = self.span_of(p)
        if symbol.type == "NUMBER":
            return Constant(value=number_value(symbol.value), span=span)
        if symbol.type == "BOOL":
            return Constant(value=bool_value(symbol.value), span=span)
        if symbol.type == "VAR":
            name, index = symbol.value
            return VariableExpr(
                variable=Variable(name=name, index=index, span=span),
                span=span,
            )
        if symbol.type == "STRING":
            return Constant(value=symbol.value, span=span)
        return SubstitutionExpr(script=symbol.value, span=span)

    def error(self, token):
        if token is None:
            position = self.base_offset + len(self.text)
            self.fail("fin inesperado de la expresión", position, position)
        position = self.base_offset + token.index
        self.fail(
            f"token inesperado en expr: {token.type}",
            position,
            self.base_offset + token.end,
        )


def parse_minitcl_expr(
    source: str,
    *,
    base_offset: int = 0,
    source_name: str = "<expr>",
    diagnostic_source: str | None = None,
    diagnostic_offset: int | None = None,
) -> Expr:
    """Fachada común de expresiones: ``ExprLexer`` + ``ExprParser`` de SLY.

    Recibe únicamente el contenido literal de la expresión (sin ``expr`` ni las
    llaves exteriores) y consume toda la entrada, de modo que los residuos como
    ``2 3`` se rechazan.
    """
    lexer = ExprLexer(
        base_offset=base_offset,
        source_name=source_name,
        read_substitution=read_substitution,
    )
    parser = ExprParser(
        text=source,
        base_offset=base_offset,
        source_name=source_name,
        diagnostic_source=diagnostic_source,
        diagnostic_offset=diagnostic_offset,
    )
    return parser.parse(lexer.tokenize(source))
