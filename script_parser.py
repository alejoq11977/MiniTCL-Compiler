"""Parser descendente recursivo de scripts MiniTcl.

Trabaja exclusivamente sobre los tokens del lexer manual (sección 4 del
cuaderno) y construye el AST estructural: ``Script → Command → Word → Part``.

El parser no sabe qué comandos existen: ``if``, ``set`` o ``proc`` son nombres
de comando, no palabras reservadas. La validación de las formas de comando
vive en ``command_analyzer.py``.
"""



from __future__ import annotations

from model import (
    Command,
    CommandSubstitution,
    Literal,
    Part,
    ParseError,
    Script,
    Span,
    Token,
    TokenCursor,
    Variable,
    Word,
    cover,
)
from script_lexer import scan_substitution, tokenize_script

class ScriptParser(TokenCursor):
    """Analizador sintáctico descendente recursivo de scripts."""

    WORD_START = {"TEXT", "VAR", "BRACED", "QOPEN", "LBRACKET"}
    PART_START = {"TEXT", "VAR", "LBRACKET"}
    AFTER_GROUPED = {"WS", "SEP", "RBRACKET", "EOF"}

    def parse(self) -> Script:
        result = self.parse_script(stop="EOF")
        self.expect("EOF")
        return result

    def parse_script(self, stop="EOF") -> Script:
        start = self.current.span
        commands = []
        self.skip("WS", "SEP")
        while self.current.kind != stop:
            if self.current.kind == "EOF":
                self.fail(f"Falta {stop}", self.current.span)
            commands.append(self.parse_command())
            if self.current.kind == stop:
                break
            self.expect("SEP")
            self.skip("WS", "SEP")
        end = commands[-1].span if commands else self.current.span
        return Script(commands=tuple(commands), span=cover(start, end))

    def parse_command(self) -> Command:
        words = [self.parse_word()]
        while self.accept("WS"):
            if self.current.kind not in self.WORD_START:
                break
            words.append(self.parse_word())
        return Command(words=tuple(words), span=cover(words[0].span, words[-1].span))

    def parse_word(self) -> Word:
        """Selecciona la producción ``word`` según el primer token."""
        kind = self.current.kind
        if kind == "BRACED":
            return self.parse_braced_word()
        if kind == "QOPEN":
            return self.parse_quoted_word()
        if kind in self.PART_START:
            return self.parse_bare_word()
        self.fail(
            f"Se esperaba el inicio de una palabra; se encontró {kind}",
            self.current.span,
        )

    def parse_bare_word(self) -> Word:
        """``bare_word = part, { part }``: partes contiguas de una sola palabra."""
        parts = []
        while self.current.kind in self.PART_START:
            parts.append(self.parse_part())
        if not parts:
            self.fail(
                f"Se esperaba una parte de palabra; se encontró {self.current.kind}",
                self.current.span,
            )
        return Word(
            parts=tuple(parts),
            mode="bare",
            span=cover(parts[0].span, parts[-1].span),
        )

    def parse_quoted_word(self) -> Word:
        """``quoted_word = QOPEN, { part }, QCLOSE``: admite cero partes."""
        opening = self.expect("QOPEN")
        parts = []
        while self.current.kind in self.PART_START:
            parts.append(self.parse_part())
        closing = self.expect("QCLOSE")
        self.require_word_boundary("palabra entre comillas")
        return Word(parts=tuple(parts), mode="quoted", span=cover(opening.span, closing.span))

    def parse_braced_word(self) -> Word:
        """``BRACED`` produce un único ``Literal`` con el contenido literal."""
        token = self.expect("BRACED")
        literal = Literal(
            text=token.value,
            span=Span(token.span.start + 1, token.span.end - 1, token.span.source),
        )
        self.require_word_boundary("palabra entre llaves")
        return Word(parts=(literal,), mode="braced", span=token.span)

    def parse_part(self) -> Part:
        """``part = TEXT | VAR | substitution``."""
        kind = self.current.kind
        if kind == "TEXT":
            token = self.expect("TEXT")
            return Literal(text=token.value, span=token.span)
        if kind == "VAR":
            token = self.expect("VAR")
            return Variable(name=token.value, index=token.index, span=token.span)
        if kind == "LBRACKET":
            return self.parse_substitution()
        self.fail(
            f"Se esperaba una parte de palabra; se encontró {kind}",
            self.current.span,
        )

    def parse_substitution(self) -> CommandSubstitution:
        """``substitution = LBRACKET, script, RBRACKET``."""
        opening = self.expect("LBRACKET")
        script = self.parse_script(stop="RBRACKET")
        closing = self.expect("RBRACKET")
        return CommandSubstitution(script=script, span=cover(opening.span, closing.span))

    def require_word_boundary(self, what: str) -> None:
        """Tras una palabra agrupada sólo puede venir WS, SEP, ']' o EOF."""
        if self.current.kind not in self.AFTER_GROUPED:
            self.fail(
                f"se esperaba un separador después de la {what}; "
                f"se encontró {self.current.kind}",
                self.current.span,
            )


def normalize_source(source: str) -> str:
    """Normaliza CRLF/CR a LF: los spans se refieren a esta fuente."""
    return source.replace("\r\n", "\n").replace("\r", "\n")


def parse_minitcl(
    source: str,
    source_name: str = "<input>",
    base_offset: int = 0,
    diagnostic_source: str | None = None,
) -> Script:
    """Fachada pública: lexer manual + ``ScriptParser`` descendente recursivo.

    ``base_offset`` desplaza los spans: al reanálisis de un bloque entre llaves
    se usa ``word.span.start + 1``, la posición de su primer carácter interior.
    ``diagnostic_source`` es el texto en el que están expresados esos offsets
    (normalmente el fichero completo), para que línea y columna sean correctas.
    """
    normalized = normalize_source(source)
    tokens = tokenize_script(normalized, source_name, base_offset)
    if diagnostic_source is None and base_offset == 0:
        diagnostic_source = normalized
    parser = ScriptParser(tokens, source=diagnostic_source, source_base_offset=0)
    return parser.parse()


def read_substitution(
    text: str,
    opening_index: int,
    base_offset: int = 0,
    source_name: str = "<expr>",
) -> tuple[Script, int]:
    """Callback que usa el lexer de SLY para leer una sustitución balanceada.

    Devuelve ``(Script, indice_local_inmediatamente_posterior_al_cierre)``.
    El script interior se analiza con el parser manual: así se respetan los
    modos de llaves y comillas y el anidamiento de sustituciones.
    """
    tokens, end = scan_substitution(text, opening_index, base_offset, source_name)
    parser = ScriptParser(tokens, source=text, source_base_offset=base_offset)
    return parser.parse(), end
