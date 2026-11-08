"""Lexer manual de scripts MiniTcl.

El lexer es *contextual*: no puede describirse con una única expresión regular
porque el significado de ``{``, ``}``, ``"``, ``[``, ``]``, ``$`` y ``#``
depende del contexto en el que aparece. Se implementa como un autómata con una
pila de marcos:

* ``command``: texto de script. ``{`` abre una palabra entre llaves (que se
  consume entera como un token ``BRACED``), ``"`` abre una palabra entre
  comillas, ``$`` abre una variable y ``[`` abre una sustitución de comando
  (que introduce un contexto de comando nuevo).
* ``quote``: interior de una palabra entre comillas. Los espacios, ``;`` y los
  saltos de línea son texto; ``$`` y ``[`` siguen abriendo sustituciones y, al
  cerrarse, se restaura el modo comillas.

Dentro de las llaves no se decodifica ningún escape: el contenido es literal y
sólo ``\\{`` y ``\\}`` se conservan con su barra para que no alteren el balanceo.
"""



from __future__ import annotations

from dataclasses import dataclass

from model import ParseError, Span, Token

try:  # pragma: no cover - depende del entorno
    from rich.console import Console

    CONSOLA = Console()
except ImportError:  # pragma: no cover - sin rich se imprime en texto plano
    CONSOLA = None

# Color por tipo de token, para leer la tabla de un vistazo.
COLOR_TOKEN = {
    "TEXT": "white",
    "WS": "dim",
    "SEP": "dim",
    "EOF": "dim",
    "VAR": "cyan",
    "BRACED": "magenta",
    "QOPEN": "green",
    "QCLOSE": "green",
    "LBRACKET": "yellow",
    "RBRACKET": "yellow",
}

COLOR_TOKEN_SLY = {
    "NUMBER": "yellow",
    "BOOL": "green",
    "VAR": "cyan",
    "STRING": "magenta",
    "CMD_SUBST": "red",
}

# --- Nombres de los tokens del contrato léxico (sección 3 del cuaderno) ------
TEXT = "TEXT"
VAR = "VAR"
BRACED = "BRACED"
QOPEN = "QOPEN"
QCLOSE = "QCLOSE"
LBRACKET = "LBRACKET"
RBRACKET = "RBRACKET"
WS = "WS"
SEP = "SEP"
EOF = "EOF"

HORIZONTAL_SPACE = " \t"

# Escapes obligatorios fuera de llaves (sección 3).
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

# Identificadores ASCII (sección 3): sólo letras ASCII, dígitos y "_".
IDENT_START = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
IDENT_CHARS = IDENT_START | frozenset("0123456789")
INDEX_CHARS = IDENT_CHARS | frozenset(".:-")


@dataclass
class _Frame:
    """Marco de la pila de contextos del lexer."""

    kind: str  # 'command' | 'quote'
    at_command_start: bool = True
    is_substitution: bool = False
    open_position: int = 0


class ScriptLexer:
    """Analizador léxico manual de scripts MiniTcl."""

    def __init__(self, source: str, source_name: str = "<input>", base_offset: int = 0):
        self.source = source
        self.source_name = source_name
        self.base_offset = base_offset
        self.position = 0
        self.tokens: list[Token] = []
        self.frames: list[_Frame] = [_Frame(kind="command", at_command_start=True)]
        self.stop_after_substitution = False
        self.finished = False

    # --- API pública -------------------------------------------------------
    def tokenize(self) -> list[Token]:
        """Analiza toda la fuente y devuelve los tokens (incluido ``EOF``)."""
        self.scan()
        end = self.base_offset + len(self.source)
        self.tokens.append(Token(EOF, "", Span(end, end, self.source_name)))
        return self.tokens

    def scan(self) -> list[Token]:
        """Recorre la fuente emitiendo tokens hasta el final o hasta el cierre
        de la sustitución abierta (modo ``stop_after_substitution``)."""
        while self.position < len(self.source) and not self.finished:
            if self.top().kind == "quote":
                self.scan_quote()
            else:
                self.scan_command()
        self.check_unterminated()
        return self.tokens

    # --- Utilidades de contexto --------------------------------------------
    def top(self) -> _Frame:
        return self.frames[-1]

    def command_frame(self) -> _Frame:
        """Marco de comando más cercano: donde vive la marca de inicio."""
        for frame in reversed(self.frames):
            if frame.kind == "command":
                return frame
        return self.frames[0]

    def mark_word_started(self) -> None:
        """Una palabra ha empezado: aquí ya no puede abrirse un comentario."""
        self.command_frame().at_command_start = False

    def emit(self, kind: str, value: str, start: int, end: int, index: str | None = None) -> None:
        span = Span(self.base_offset + start, self.base_offset + end, self.source_name)
        self.tokens.append(Token(kind, value, span, index))

    def span_at(self, start: int, end: int | None = None) -> Span:
        if end is None:
            end = start + 1
        return Span(self.base_offset + start, self.base_offset + end, self.source_name)

    def fail(self, message: str, start: int, end: int | None = None) -> None:
        """Lanza un ``ParseError`` con la posición exacta del problema."""
        raise ParseError(message, self.span_at(start, end), self.source, start)

    # --- Bucle principal ----------------------------------------------------
    def scan_command(self) -> None:
        char = self.source[self.position]
        if char in HORIZONTAL_SPACE:
            self.scan_whitespace()
        elif char == "\n" or char == ";":
            self.scan_separator()
        elif char == "#" and self.top().at_command_start:
            self.skip_comment()
        elif char == "{":
            self.scan_braced_word()
        elif char == '"':
            self.scan_quote_open()
        elif char == "$":
            self.scan_variable()
        elif char == "[":
            self.scan_substitution_open()
        elif char == "]":
            self.scan_substitution_close()
        else:
            self.scan_text()

    def scan_whitespace(self) -> None:
        start = self.position
        while self.position < len(self.source) and self.source[self.position] in HORIZONTAL_SPACE:
            self.position += 1
        self.emit(WS, self.source[start:self.position], start, self.position)

    def scan_separator(self) -> None:
        start = self.position
        char = self.source[self.position]
        self.position += 1
        self.emit(SEP, char, start, self.position)
        # Tras un separador puede empezar un comando nuevo (y un comentario).
        self.command_frame().at_command_start = True

    def skip_comment(self) -> None:
        """El comentario termina en el salto de línea; el salto sigue siendo SEP."""
        while self.position < len(self.source) and self.source[self.position] != "\n":
            self.position += 1

    def scan_braced_word(self) -> None:
        """Palabra entre llaves: se consume entera contando el balanceo."""
        start = self.position
        self.position += 1  # '{'
        content_start = self.position
        depth = 1
        closed = False
        while self.position < len(self.source):
            char = self.source[self.position]
            if char == "\\":
                following = self.source[self.position + 1] if self.position + 1 < len(self.source) else ""
                # Sólo \{ y \} son especiales: se conservan con su barra y no
                # alteran la profundidad. Cualquier otra secuencia se conserva
                # tal cual, porque dentro de las llaves no se decodifica nada.
                self.position += 2 if following else 1
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    self.position += 1
                    closed = True
                    break
            self.position += 1
        if not closed:
            self.fail("falta la llave de cierre '}'", start)
        content = self.source[content_start:self.position - 1]
        self.mark_word_started()
        self.emit(BRACED, content, start, self.position)

    def scan_quote_open(self) -> None:
        start = self.position
        self.position += 1  # '"'
        self.mark_word_started()
        self.emit(QOPEN, '"', start, self.position)
        self.frames.append(_Frame(kind="quote", at_command_start=False, open_position=start))

    def scan_quote(self) -> None:
        """Interior de una palabra entre comillas."""
        start = self.position
        chars: list[str] = []
        while self.position < len(self.source):
            char = self.source[self.position]
            if char == '"' or char == "$" or char == "[":
                break
            if char == "\\":
                chars.append(self.decode_escape())
                continue
            chars.append(char)
            self.position += 1
        if chars:
            self.emit(TEXT, "".join(chars), start, self.position)
        if self.position >= len(self.source):
            return
        char = self.source[self.position]
        if char == '"':
            close_start = self.position
            self.position += 1
            self.emit(QCLOSE, '"', close_start, self.position)
            self.frames.pop()
        elif char == "$":
            self.scan_variable()
        else:
            self.scan_substitution_open()

    def scan_text(self) -> None:
        """Fragmento literal de una palabra sin agrupar."""
        start = self.position
        chars: list[str] = []
        while self.position < len(self.source):
            char = self.source[self.position]
            if char in HORIZONTAL_SPACE or char in "\n;":
                break
            if char in "$[":
                break
            if char == "]":
                break
            if char == "{" or char == "}":
                self.fail(
                    f"'{char}' no puede aparecer en una palabra sin agrupar; "
                    f"escríbala como '\\{char}'",
                    self.position,
                )
            if char == '"':
                self.fail(
                    "'\"' no puede aparecer en una palabra sin agrupar; "
                    "escríbala como '\\\"'",
                    self.position,
                )
            if char == "\\":
                chars.append(self.decode_escape())
                continue
            chars.append(char)
            self.position += 1
        self.mark_word_started()
        self.emit(TEXT, "".join(chars), start, self.position)

    def decode_escape(self) -> str:
        start = self.position
        self.position += 1  # '\'
        if self.position >= len(self.source):
            self.fail("escape '\\' al final de la fuente", start)
        char = self.source[self.position]
        if char == "\n":
            self.fail(
                "la continuación con barra y salto de línea está fuera del perfil obligatorio",
                start,
            )
        if char not in ESCAPES:
            self.fail(f"escape desconocido '\\{char}'", start)
        self.position += 1
        return ESCAPES[char]

    def scan_variable(self) -> None:
        """Variable escalar (``$x``), con índice (``$a(3)``) o entre llaves (``${x}``)."""
        start = self.position
        self.position += 1  # '$'
        if self.position < len(self.source) and self.source[self.position] == "{":
            self.position += 1
            name_start = self.position
            while self.position < len(self.source) and self.source[self.position] in IDENT_CHARS:
                self.position += 1
            name = self.source[name_start:self.position]
            if not name:
                self.fail("'${' sin nombre de variable", start)
            if self.position >= len(self.source) or self.source[self.position] != "}":
                self.fail("falta '}' en '${...}'", start)
            self.position += 1
            self.mark_word_started()
            self.emit(VAR, name, start, self.position)
            return
        if self.position < len(self.source) and self.source[self.position] in IDENT_START:
            name_start = self.position
            while self.position < len(self.source) and self.source[self.position] in IDENT_CHARS:
                self.position += 1
            name = self.source[name_start:self.position]
            index = None
            if self.position < len(self.source) and self.source[self.position] == "(":
                index_start = self.position + 1
                scan = index_start
                while scan < len(self.source) and self.source[scan] in INDEX_CHARS:
                    scan += 1
                if scan == index_start:
                    self.fail(
                        "índice de arreglo vacío o fuera del perfil léxico",
                        self.position,
                    )
                if scan >= len(self.source) or self.source[scan] != ")":
                    self.fail("falta ')' en la referencia a un arreglo", self.position)
                index = self.source[index_start:scan]
                self.position = scan + 1
            self.mark_word_started()
            self.emit(VAR, name, start, self.position, index=index)
            return
        self.fail("'$' debe ir seguido de un nombre de variable", start)

    def scan_substitution_open(self) -> None:
        start = self.position
        self.position += 1  # '['
        self.mark_word_started()
        self.emit(LBRACKET, "[", start, self.position)
        # Al entrar en '[' empieza un contexto de comando nuevo.
        self.frames.append(
            _Frame(kind="command", at_command_start=True, is_substitution=True, open_position=start)
        )

    def scan_substitution_close(self) -> None:
        frame = self.top()
        if not frame.is_substitution:
            self.fail("']' fuera de contexto: no hay ninguna sustitución abierta", self.position)
        start = self.position
        self.position += 1  # ']'
        self.emit(RBRACKET, "]", start, self.position)
        self.frames.pop()
        if self.stop_after_substitution and len(self.frames) == 1:
            self.finished = True

    def check_unterminated(self) -> None:
        if len(self.frames) == 1:
            return
        frame = self.top()
        if frame.kind == "quote":
            self.fail("falta la comilla de cierre '\"'", frame.open_position)
        self.fail("falta el corchete de cierre ']'", frame.open_position)


def tokenize_script(source: str, source_name: str = "<input>", base_offset: int = 0) -> list[Token]:
    """Analiza una fuente completa y devuelve sus tokens."""
    return ScriptLexer(source, source_name, base_offset).tokenize()


def tipo_de_token(token) -> str:
    """Nombre del tipo de un token, sea del lexer manual o de SLY."""
    return token.kind if hasattr(token, "kind") else token.type


def resumen_tokens(tokens) -> str:
    """Recuento de tokens por tipo: ``TEXT×3, WS×2, EOF×1``."""
    conteo: dict[str, int] = {}
    for token in tokens:
        tipo = tipo_de_token(token)
        conteo[tipo] = conteo.get(tipo, 0) + 1
    return ", ".join(f"{tipo}×{n}" for tipo, n in sorted(conteo.items()))


def _escapar(texto: str) -> str:
    """Escapa los corchetes para el marcado de rich."""
    return texto.replace("[", "\\[")


def show_tokens(tokens, resumen: bool = True) -> None:
    """Imprime la secuencia de tokens del analizador léxico.

    Se muestran las dos familias de tokens, porque su contrato es distinto:
    los del lexer manual tienen ``kind``/``value``/``span`` y los de SLY
    ``type``/``value``/``lineno``/``index``/``end``.  El ``repr`` se recorta
    porque el token ``CMD_SUBST`` lleva dentro un ``Script`` completo.
    """
    for token in tokens:
        value = repr(token.value)
        if len(value) > 40:
            value = value[:37] + "..."
        if hasattr(token, "kind"):
            tipo = token.kind
            posicion = f"[{token.span.start}:{token.span.end}] {token.span.source}"
            color = COLOR_TOKEN.get(tipo)
        else:
            tipo = token.type
            posicion = f"línea {token.lineno} pos {token.index}"
            color = COLOR_TOKEN_SLY.get(tipo)
        if CONSOLA is not None and color:
            CONSOLA.print(
                f"  [bold {color}]{tipo.ljust(10)}[/] "
                f"{_escapar(value).ljust(24)} {_escapar(posicion)}"
            )
        else:
            print(f"  {tipo:10} {value:24} {posicion}")
    if resumen:
        print(f"  {len(list(tokens))} tokens: {resumen_tokens(tokens)}")


def show_token_ruler(fuente: str, tokens) -> None:
    """El fuente con los límites de cada token marcados debajo.

    Es la vista más didáctica del análisis léxico: se ve de un vistazo dónde
    acaba cada palabra y qué se considera un token.
    """
    print("--- el fuente y los límites de cada token ---")
    print(fuente)
    plano = fuente.replace("\n", " ")
    marca = [" "] * len(plano)
    for token in tokens:
        if not hasattr(token, "kind") or token.kind in ("WS", "SEP", "EOF"):
            continue
        for posicion in range(token.span.start, min(token.span.end, len(plano))):
            marca[posicion] = "^"
    print("".join(marca).rstrip())


def scan_substitution(
    text: str,
    opening_index: int,
    base_offset: int = 0,
    source_name: str = "<expr>",
) -> tuple[list[Token], int]:
    """Escanea el script balanceado que empieza en ``opening_index`` (un ``[``).

    Devuelve ``(tokens_internos, indice_local)`` donde ``indice_local`` es la
    posición inmediatamente posterior al ``]`` de cierre. Los tokens internos
    terminan en ``EOF`` para que el cursor pueda consumirlos.
    """
    lexer = ScriptLexer(text, source_name, base_offset)
    lexer.position = opening_index
    lexer.stop_after_substitution = True
    lexer.scan()
    inner = list(lexer.tokens[1:-1])  # se descartan LBRACKET y RBRACKET
    end = lexer.position
    inner.append(Token(EOF, "", Span(base_offset + end, base_offset + end, source_name)))
    return inner, end
