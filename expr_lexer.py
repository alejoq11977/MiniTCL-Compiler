"""Lexer de expresiones MiniTcl sobre ``sly.Lexer``.

El contrato es el de la sección 5 del cuaderno:

* Los patrones largos se definen antes de los cortos (``**`` antes de ``*``,
  ``<=`` antes de ``<``, ``!=`` antes de ``!``). El regex maestro de SLY se
  construye con las definiciones en el orden en que aparecen en el cuerpo de
  la clase, de modo que el orden es significativo.
* ``CMD_SUBST`` no se reconoce con una expresión regular: al encontrar ``[``
  se delega la lectura balanceada al lexer manual mediante un callback, que
  devuelve el ``Script`` ya analizado y el índice posterior al ``]``.
* ``VAR`` admite la forma escalar, la forma entre llaves y la forma con índice
  literal de arreglo. Como ``sly.Token`` no admite campos extra, el valor del
  token es la pareja ``(nombre, índice)``.
"""



from __future__ import annotations

from sly import Lexer

from model import ParseError, Span

IDENT_START = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
IDENT_CHARS = IDENT_START | frozenset("0123456789")
INDEX_CHARS = IDENT_CHARS | frozenset(".:-")

ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "\\": "\\",
    " ": " ",
    "$": "$",
    "[": "[",
    "]": "]",
    "{": "{",
    "}": "}",
    '"': '"',
    ";": ";",
    "#": "#",
}


class ExprLexer(Lexer):
    """Lexer de la gramática de expresiones (sección 5)."""

    tokens = {
        OR,
        AND,
        EQ,
        NE,
        STREQ,
        STRNE,
        LT,
        LE,
        GT,
        GE,
        PLUS,
        MINUS,
        TIMES,
        DIVIDE,
        MOD,
        POWER,
        NOT,
        LPAREN,
        RPAREN,
        NUMBER,
        BOOL,
        VAR,
        STRING,
        CMD_SUBST,
    }

    ignore = " \t\r\n"

    # --- Operadores: primero los patrones largos ---------------------------
    POWER = r"\*\*"
    TIMES = r"\*"
    LE = r"<="
    GE = r">="
    NE = r"!="
    NOT = r"!"
    LT = r"<"
    GT = r">"
    EQ = r"=="
    OR = r"\|\|"
    AND = r"&&"
    PLUS = r"\+"
    MINUS = r"-"
    DIVIDE = r"/"
    MOD = r"%"
    LPAREN = r"\("
    RPAREN = r"\)"

    # --- Literales ----------------------------------------------------------
    NUMBER = r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
    BOOL = r"(?:true|false|yes|no|on|off)\b"
    STREQ = r"eq\b"
    STRNE = r"ne\b"

    def __init__(
        self,
        base_offset: int = 0,
        source_name: str = "<expr>",
        read_substitution=None,
    ):
        self.base_offset = base_offset
        self.source_name = source_name
        self.read_substitution = read_substitution

    # --- Utilidades ---------------------------------------------------------
    def fail(self, message: str, index: int) -> None:
        position = self.base_offset + index
        raise ParseError(
            message,
            Span(position, position + 1, self.source_name),
            self.text if hasattr(self, "text") else None,
            index,
        )

    # --- Reglas con acción --------------------------------------------------
    @_(r"\$")
    def VAR(self, t):
        """Variable escalar ``$x``, entre llaves ``${x}`` o de arreglo ``$a(3)``."""
        text = self.text
        index = t.index + 1
        index_value = None
        if index < len(text) and text[index] == "{":
            end = index + 1
            while end < len(text) and text[end] in IDENT_CHARS:
                end += 1
            name = text[index + 1: end]
            if not name:
                self.fail("'${' sin nombre de variable", t.index)
            if end >= len(text) or text[end] != "}":
                self.fail("falta '}' en '${...}'", t.index)
            end += 1
        else:
            if index >= len(text) or text[index] not in IDENT_START:
                self.fail("'$' debe ir seguido de un nombre de variable", t.index)
            end = index
            while end < len(text) and text[end] in IDENT_CHARS:
                end += 1
            name = text[index:end]
            if end < len(text) and text[end] == "(":
                index_start = end + 1
                scan = index_start
                while scan < len(text) and text[scan] in INDEX_CHARS:
                    scan += 1
                if scan == index_start:
                    self.fail("índice de arreglo vacío o fuera del perfil léxico", end)
                if scan >= len(text) or text[scan] != ")":
                    self.fail("falta ')' en la referencia a un arreglo", end)
                index_value = text[index_start:scan]
                end = scan + 1
        self.index = end
        t.end = end
        t.value = (name, index_value)
        return t

    @_(r'"')
    def STRING(self, t):
        """Cadena literal entre comillas: sin interpolación en este perfil."""
        text = self.text
        index = t.index + 1
        chars: list[str] = []
        while index < len(text):
            char = text[index]
            if char == '"':
                index += 1
                break
            if char in "$[":
                self.fail(
                    f"'{char}' no puede aparecer sin escapar dentro de una cadena de expr",
                    index,
                )
            if char == "\\":
                following = text[index + 1] if index + 1 < len(text) else ""
                if following not in ESCAPES:
                    self.fail(f"escape desconocido '\\{following}'", index)
                chars.append(ESCAPES[following])
                index += 2
                continue
            chars.append(char)
            index += 1
        else:
            self.fail("falta la comilla de cierre '\"'", t.index)
        self.index = index
        t.end = index
        t.value = "".join(chars)
        return t

    @_(r"\[")
    def CMD_SUBST(self, t):
        """Sustitución de comando: la lee el lexer manual y devuelve un ``Script``."""
        if self.read_substitution is None:
            self.fail("no hay callback para leer la sustitución de comando", t.index)
        script, end = self.read_substitution(
            self.text, t.index, self.base_offset, self.source_name
        )
        # El lexer continúa justo después del ']' y el token cubre todo el texto.
        self.index = end
        t.end = end
        t.value = script
        self.lineno += self.text.count("\n", t.index, end)
        return t

    def error(self, token):
        position = self.base_offset + token.index
        raise ParseError(
            "carácter inválido o token aún no implementado en expr",
            Span(position, position + 1, self.source_name),
            getattr(self, "text", None),
            token.index,
        )
