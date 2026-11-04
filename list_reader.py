"""Lector de listas MiniTcl (sección 7 del cuaderno).

El contenido de una lista **no es un script**: ``$x``, ``[comando]`` y ``;`` son
datos, sin sustituciones ni separación de comandos. El salto de línea separa
elementos igual que un espacio.

    list_value = { LIST_WS }, [ element, { LIST_WS, element } ], { LIST_WS } ;
    element    = LIST_BRACED | LIST_QUOTED | LIST_BARE ;

El lector balancea las llaves, elimina las agrupaciones y procesa los escapes
admitidos fuera de llaves. El contrato esencial es::

    parse_list(format_list(values)) == values
"""



from __future__ import annotations

from model import ParseError, Span

LIST_WS = "LIST_WS"
LIST_BRACED = "LIST_BRACED"
LIST_QUOTED = "LIST_QUOTED"
LIST_BARE = "LIST_BARE"

WHITESPACE = " \t\n"

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


class ListReader:
    """Analizador léxico del contenido de una lista."""

    def __init__(self, text: str, source_name: str = "<list>", base_offset: int = 0):
        self.text = text
        self.source_name = source_name
        self.base_offset = base_offset
        self.position = 0

    # --- Utilidades ---------------------------------------------------------
    def fail(self, message: str, start: int, end: int | None = None) -> None:
        if end is None:
            end = start + 1
        span = Span(self.base_offset + start, self.base_offset + end, self.source_name)
        raise ParseError(message, span, self.text, start)

    # --- API ----------------------------------------------------------------
    def parse(self) -> list[str]:
        values: list[str] = []
        self.skip_whitespace()
        while self.position < len(self.text):
            values.append(self.parse_element())
            if self.position >= len(self.text):
                break
            # Tras una agrupación (o tras cualquier elemento) sólo puede venir
            # un blanco o el fin de la lista.
            if self.text[self.position] not in WHITESPACE:
                self.fail(
                    "se esperaba un blanco o el fin de la lista",
                    self.position,
                )
            self.skip_whitespace()
        return values

    def skip_whitespace(self) -> None:
        while self.position < len(self.text) and self.text[self.position] in WHITESPACE:
            self.position += 1

    def parse_element(self) -> str:
        char = self.text[self.position]
        if char == "{":
            return self.parse_braced()
        if char == '"':
            return self.parse_quoted()
        return self.parse_bare()

    def parse_braced(self) -> str:
        """Elemento entre llaves: balanceado y literal."""
        start = self.position
        self.position += 1
        content_start = self.position
        depth = 1
        closed = False
        while self.position < len(self.text):
            char = self.text[self.position]
            if char == "\\":
                following = (
                    self.text[self.position + 1] if self.position + 1 < len(self.text) else ""
                )
                self.position += 2 if following else 1
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    content = self.text[content_start:self.position]
                    self.position += 1
                    closed = True
                    break
            self.position += 1
        if not closed:
            self.fail("falta la llave de cierre '}' de un elemento de lista", start)
        return content

    def parse_quoted(self) -> str:
        """Elemento entre comillas: se procesan los escapes."""
        start = self.position
        self.position += 1
        chars: list[str] = []
        while self.position < len(self.text):
            char = self.text[self.position]
            if char == '"':
                self.position += 1
                return "".join(chars)
            if char == "\\":
                chars.append(self.decode_escape())
                continue
            chars.append(char)
            self.position += 1
        self.fail("falta la comilla de cierre '\"' de un elemento de lista", start)

    def parse_bare(self) -> str:
        """Elemento desnudo: sin blancos y sin llaves ni comillas sin escapar."""
        start = self.position
        chars: list[str] = []
        while self.position < len(self.text):
            char = self.text[self.position]
            if char in WHITESPACE:
                break
            if char in "{}":
                self.fail(
                    f"'{char}' no puede aparecer en un elemento sin agrupar",
                    self.position,
                )
            if char == '"':
                self.fail(
                    "'\"' no puede aparecer en un elemento sin agrupar",
                    self.position,
                )
            if char == "\\":
                chars.append(self.decode_escape())
                continue
            chars.append(char)
            self.position += 1
        if not chars:
            self.fail("se esperaba un elemento de lista", start)
        return "".join(chars)

    def decode_escape(self) -> str:
        start = self.position
        self.position += 1
        if self.position >= len(self.text):
            self.fail("escape '\\' al final de la lista", start)
        char = self.text[self.position]
        if char not in ESCAPES:
            self.fail(f"escape desconocido '\\{char}'", start)
        self.position += 1
        return ESCAPES[char]


def parse_list(text: str, source_name: str = "<list>", base_offset: int = 0) -> list[str]:
    """Analiza el contenido de una lista y devuelve sus elementos."""
    return ListReader(text, source_name, base_offset).parse()


def format_list(values) -> str:
    """Serializa una lista de forma que ``parse_list`` la reconstruya.

    No se usa ``" ".join(values)``: los elementos con espacios, llaves o
    cadenas vacías deben conservarse.
    """
    parts = []
    for value in values:
        if value == "":
            parts.append("{}")
        elif any(char in value for char in ' \t\n{}"\\;'):
            escaped = (
                value.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("{", "\\{")
                .replace("}", "\\}")
                .replace(";", "\\;")
            )
            parts.append('"' + escaped + '"')
        else:
            parts.append(value)
    return " ".join(parts)
