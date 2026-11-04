"""Validación de comandos y análisis estático de cuerpos y condiciones.

El parser estructural (sección 4) reconoce scripts, comandos y palabras, pero
no sabe qué comandos existen. Este módulo hace la segunda pasada:

1. Comprueba la **forma** de cada comando (sección 6): aridad y estructura de
   los incorporados.
2. Reanaliza, sin ejecutarlos, los argumentos que lo requieren (sección 13):
   las condiciones y los cuerpos de ``expr``, ``if``, ``elseif``, ``while``,
   ``for``, ``foreach``, ``proc`` y ``catch``.

El AST estructural original se conserva: esta pasada lo *anota* con los AST
adicionales, nunca lo sustituye.
"""



from __future__ import annotations

import re
from dataclasses import dataclass

from expr_parser import parse_minitcl_expr
from list_reader import parse_list
from model import (
    Command,
    Expr,
    Literal,
    ParseError,
    Script,
    Span,
    Word,
)
from script_parser import parse_minitcl

NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\([A-Za-z0-9_.:-]+\))?$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Formas de los incorporados (sección 6 y biblioteca mínima de datos).
BUILTIN_FORMS = {
    "set": "set_cmd",
    "unset": "unset_cmd",
    "incr": "incr_cmd",
    "append": "append_cmd",
    "puts": "puts_cmd",
    "expr": "expr_cmd",
    "if": "if_cmd",
    "while": "while_cmd",
    "for": "for_cmd",
    "foreach": "foreach_cmd",
    "proc": "proc_cmd",
    "return": "return_cmd",
    "break": "break_cmd",
    "continue": "continue_cmd",
    "global": "global_cmd",
    "catch": "catch_cmd",
    "error": "error_cmd",
    "list": "list_cmd",
    "llength": "llength_cmd",
    "lindex": "lindex_cmd",
    "lappend": "lappend_cmd",
    "lset": "lset_cmd",
    "dict": "dict_cmd",
    "string": "string_cmd",
    "split": "split_cmd",
    "join": "join_cmd",
}

DICT_SUBCOMMANDS = {"create", "get", "exists", "set"}
STRING_SUBCOMMANDS = {"length", "tolower", "toupper", "compare"}


@dataclass(frozen=True)
class ArgumentAnalysis:
    """Vincula una palabra del comando con el AST adicional que produce."""

    word_index: int
    kind: str  # 'expr' | 'script' | 'list' | 'name' | 'identifier' | 'word'
    span: Span
    value: object = None


@dataclass(frozen=True)
class CommandAnalysis:
    """Resultado de validar un comando y de reanalizar sus argumentos."""

    command: Command
    form: str
    arguments: tuple[ArgumentAnalysis, ...] = ()
    substitutions: tuple["ScriptAnalysis", ...] = ()
    bodies: tuple["ScriptAnalysis", ...] = ()


@dataclass(frozen=True)
class ScriptAnalysis:
    """Resultado de validar un script completo."""

    script: Script
    commands: tuple[CommandAnalysis, ...] = ()


class _Context:
    """Datos compartidos por la validación: fuente y nombre del fichero."""

    def __init__(self, source: str | None, source_name: str):
        self.source = source
        self.source_name = source_name
        # Análisis estático de los cuerpos que se hayan reanalizado.
        self.bodies: list[ScriptAnalysis] = []

    def fail(self, message: str, span: Span) -> None:
        raise ParseError(message, span, self.source, span.start)


def literal_text(word: Word) -> str | None:
    """Texto literal de una palabra sin interpolación, o ``None`` si la tiene."""
    if word.mode == "braced":
        return word.parts[0].text
    if len(word.parts) == 1 and isinstance(word.parts[0], Literal):
        return word.parts[0].text
    return None


def analyze_command(
    command: Command,
    source: str | None = None,
    source_name: str = "<input>",
) -> CommandAnalysis:
    """Valida la forma de un comando y reanalyze sus argumentos estáticos."""
    context = _Context(source, source_name)
    words = command.words
    name = literal_text(words[0])
    if name is None:
        context.fail(
            "el nombre del comando debe ser literal: los nombres calculados "
            "están fuera del perfil estático del curso",
            words[0].span,
        )
    form = BUILTIN_FORMS.get(name, "call_cmd")
    arguments: list[ArgumentAnalysis] = []
    substitutions: list[ScriptAnalysis] = []
    _collect_substitutions(command, context, substitutions)
    handler = _HANDLERS[form]
    handler(command, name, context, arguments)
    return CommandAnalysis(
        command=command,
        form=form,
        arguments=tuple(arguments),
        substitutions=tuple(substitutions),
        bodies=tuple(context.bodies),
    )


def analyze_script(
    script: Script,
    source: str | None = None,
    source_name: str = "<input>",
) -> ScriptAnalysis:
    """Valida todos los comandos de un script, incluidas las sustituciones."""
    analyses = tuple(
        analyze_command(command, source, source_name) for command in script.commands
    )
    return ScriptAnalysis(script=script, commands=analyses)


def analyze_minitcl(source: str, source_name: str = "<input>") -> ScriptAnalysis:
    """Fachada: analiza la estructura y valida las formas de comando."""
    script = parse_minitcl(source, source_name)
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    return analyze_script(script, normalized, source_name)


# --- Utilidades de validación ------------------------------------------------
def _expect_count(
    words: tuple[Word, ...],
    minimum: int,
    maximum: int | None,
    form: str,
    context: _Context,
) -> None:
    count = len(words)
    if count < minimum or (maximum is not None and count > maximum):
        if maximum is None:
            expected = f"al menos {minimum}"
        elif minimum == maximum:
            expected = f"{minimum}"
        else:
            expected = f"entre {minimum} y {maximum}"
        context.fail(
            f"arity mismatch in {form}: se esperaba {expected} palabra(s) "
            f"y se encontraron {count}",
            words[0].span,
        )


def _expect_name(words: tuple[Word, ...], index: int, form: str, context: _Context) -> str:
    """Nombre de variable: literal ``identificador`` o ``identificador(indice)``."""
    if index >= len(words):
        context.fail(f"arity mismatch in {form}: falta el nombre", words[0].span)
    text = literal_text(words[index])
    if text is None or not NAME_PATTERN.match(text):
        context.fail(
            f"se esperaba un nombre de variable literal en {form}",
            words[index].span,
        )
    return text


def _expect_identifier(words: tuple[Word, ...], index: int, form: str, context: _Context) -> str:
    if index >= len(words):
        context.fail(f"arity mismatch in {form}: falta el identificador", words[0].span)
    text = literal_text(words[index])
    if text is None or not IDENTIFIER_PATTERN.match(text):
        context.fail(
            f"se esperaba un identificador literal en {form}",
            words[index].span,
        )
    return text


def _expect_braced(words: tuple[Word, ...], index: int, form: str, context: _Context) -> Word:
    """Un argumento ``test``, ``body`` o ``parameters`` debe ir entre llaves."""
    if index >= len(words):
        context.fail(f"arity mismatch in {form}: falta el argumento", words[0].span)
    word = words[index]
    if word.mode != "braced":
        context.fail(
            f"se esperaba un bloque entre llaves en {form}",
            word.span,
        )
    return word


def _analyze_expression(
    word: Word,
    context: _Context,
    arguments: list[ArgumentAnalysis],
    word_index: int,
) -> Expr:
    """Entrega el contenido literal de un bloque a la fachada de SLY."""
    inner = word.parts[0].text
    expression = parse_minitcl_expr(
        inner,
        base_offset=word.span.start + 1,
        source_name=word.span.source,
        diagnostic_source=context.source,
        diagnostic_offset=word.span.start + 1,
    )
    arguments.append(
        ArgumentAnalysis(
            word_index=word_index,
            kind="expr",
            span=word.span,
            value=expression,
        )
    )
    return expression


def _analyze_body(
    word: Word,
    context: _Context,
    arguments: list[ArgumentAnalysis],
    word_index: int,
) -> Script:
    """Entrega el contenido literal de un bloque al parser manual.

    El cuerpo se analiza como script *y* se valida: un error de sintaxis o de
    forma dentro de un cuerpo estático se reporta aunque la rama no se tome.
    """
    inner = word.parts[0].text
    script = parse_minitcl(
        inner,
        word.span.source,
        base_offset=word.span.start + 1,
        diagnostic_source=context.source,
    )
    arguments.append(
        ArgumentAnalysis(word_index=word_index, kind="script", span=word.span, value=script)
    )
    context.bodies.append(analyze_script(script, context.source, word.span.source))
    return script


def _collect_substitutions(
    command: Command,
    context: _Context,
    substitutions: list[ScriptAnalysis],
) -> None:
    """Los corchetes ya producen un ``Script``: también se validan."""
    for word in command.words:
        for part in word.parts:
            if hasattr(part, "script"):
                substitutions.append(
                    analyze_script(part.script, context.source, part.script.span.source)
                )


# --- Manejadores de forma ----------------------------------------------------
def _handle_call(command, name, context, arguments):
    """``call_cmd = word, { word }``: la forma estructural general."""
    _expect_count(command.words, 1, None, "call_cmd", context)
    for index, word in enumerate(command.words):
        arguments.append(
            ArgumentAnalysis(word_index=index, kind="word", span=word.span, value=word)
        )


def _handle_set(command, name, context, arguments):
    _expect_count(command.words, 2, 3, "set_cmd", context)
    target = _expect_name(command.words, 1, "set_cmd", context)
    arguments.append(
        ArgumentAnalysis(word_index=1, kind="name", span=command.words[1].span, value=target)
    )
    if len(command.words) == 3:
        arguments.append(
            ArgumentAnalysis(
                word_index=2, kind="word", span=command.words[2].span, value=command.words[2]
            )
        )


def _handle_unset(command, name, context, arguments):
    _expect_count(command.words, 2, 2, "unset_cmd", context)
    target = _expect_name(command.words, 1, "unset_cmd", context)
    arguments.append(
        ArgumentAnalysis(word_index=1, kind="name", span=command.words[1].span, value=target)
    )


def _handle_incr(command, name, context, arguments):
    _expect_count(command.words, 2, 3, "incr_cmd", context)
    target = _expect_name(command.words, 1, "incr_cmd", context)
    arguments.append(
        ArgumentAnalysis(word_index=1, kind="name", span=command.words[1].span, value=target)
    )
    if len(command.words) == 3:
        arguments.append(
            ArgumentAnalysis(
                word_index=2, kind="word", span=command.words[2].span, value=command.words[2]
            )
        )


def _handle_append(command, name, context, arguments):
    _expect_count(command.words, 3, None, "append_cmd", context)
    target = _expect_name(command.words, 1, "append_cmd", context)
    arguments.append(
        ArgumentAnalysis(word_index=1, kind="name", span=command.words[1].span, value=target)
    )
    for index in range(2, len(command.words)):
        arguments.append(
            ArgumentAnalysis(
                word_index=index, kind="word", span=command.words[index].span,
                value=command.words[index],
            )
        )


def _handle_puts(command, name, context, arguments):
    _expect_count(command.words, 2, 3, "puts_cmd", context)
    index = 1
    if literal_text(command.words[index]) == "-nonewline":
        arguments.append(
            ArgumentAnalysis(
                word_index=index,
                kind="word",
                span=command.words[index].span,
                value="-nonewline",
            )
        )
        index += 1
    if index >= len(command.words):
        context.fail("arity mismatch in puts_cmd: falta el texto", command.words[0].span)
    arguments.append(
        ArgumentAnalysis(
            word_index=index,
            kind="word",
            span=command.words[index].span,
            value=command.words[index],
        )
    )


def _handle_expr(command, name, context, arguments):
    _expect_count(command.words, 2, 2, "expr_cmd", context)
    block = _expect_braced(command.words, 1, "expr_cmd", context)
    _analyze_expression(block, context, arguments, 1)


def _handle_if(command, name, context, arguments):
    words = command.words
    if len(words) < 3:
        context.fail(
            "arity mismatch in if_cmd: se esperaba 'if' test [then] body "
            "[elseif test [then] body]... [else body]",
            words[0].span,
        )
    index = 1
    test = _expect_braced(words, index, "if_cmd", context)
    _analyze_expression(test, context, arguments, index)
    index += 1
    if index < len(words) and literal_text(words[index]) == "then":
        index += 1
    body = _expect_braced(words, index, "if_cmd", context)
    _analyze_body(body, context, arguments, index)
    index += 1
    while index < len(words) and literal_text(words[index]) == "elseif":
        index += 1
        test = _expect_braced(words, index, "if_cmd", context)
        _analyze_expression(test, context, arguments, index)
        index += 1
        if index < len(words) and literal_text(words[index]) == "then":
            index += 1
        body = _expect_braced(words, index, "if_cmd", context)
        _analyze_body(body, context, arguments, index)
        index += 1
    if index < len(words) and literal_text(words[index]) == "else":
        index += 1
        if index >= len(words):
            context.fail("falta el cuerpo de la rama 'else'", words[0].span)
        body = _expect_braced(words, index, "if_cmd", context)
        _analyze_body(body, context, arguments, index)
        index += 1
    if index != len(words):
        context.fail(
            f"arity mismatch in if_cmd: sobran {len(words) - index} palabra(s)",
            words[index].span,
        )


def _handle_while(command, name, context, arguments):
    _expect_count(command.words, 3, 3, "while_cmd", context)
    test = _expect_braced(command.words, 1, "while_cmd", context)
    _analyze_expression(test, context, arguments, 1)
    body = _expect_braced(command.words, 2, "while_cmd", context)
    _analyze_body(body, context, arguments, 2)


def _handle_for(command, name, context, arguments):
    _expect_count(command.words, 5, 5, "for_cmd", context)
    initial = _expect_braced(command.words, 1, "for_cmd", context)
    _analyze_body(initial, context, arguments, 1)
    test = _expect_braced(command.words, 2, "for_cmd", context)
    _analyze_expression(test, context, arguments, 2)
    step = _expect_braced(command.words, 3, "for_cmd", context)
    _analyze_body(step, context, arguments, 3)
    body = _expect_braced(command.words, 4, "for_cmd", context)
    _analyze_body(body, context, arguments, 4)


def _handle_foreach(command, name, context, arguments):
    _expect_count(command.words, 4, 4, "foreach_cmd", context)
    variable = _expect_identifier(command.words, 1, "foreach_cmd", context)
    arguments.append(
        ArgumentAnalysis(
            word_index=1, kind="identifier", span=command.words[1].span, value=variable
        )
    )
    arguments.append(
        ArgumentAnalysis(
            word_index=2, kind="word", span=command.words[2].span, value=command.words[2]
        )
    )
    body = _expect_braced(command.words, 3, "foreach_cmd", context)
    _analyze_body(body, context, arguments, 3)


def _handle_proc(command, name, context, arguments):
    _expect_count(command.words, 4, 4, "proc_cmd", context)
    procedure = _expect_identifier(command.words, 1, "proc_cmd", context)
    if procedure in BUILTIN_FORMS:
        context.fail(
            f"no se puede redefinir el incorporado '{procedure}'",
            command.words[1].span,
        )
    arguments.append(
        ArgumentAnalysis(
            word_index=1, kind="identifier", span=command.words[1].span, value=procedure
        )
    )
    parameters = _expect_braced(command.words, 2, "proc_cmd", context)
    names = parse_list(parameters.parts[0].text, parameters.span.source)
    seen: set[str] = set()
    for parameter in names:
        if not IDENTIFIER_PATTERN.match(parameter):
            context.fail(
                f"el parámetro '{parameter}' no es un identificador válido",
                parameters.span,
            )
        if parameter in seen:
            context.fail(
                f"el parámetro '{parameter}' está duplicado",
                parameters.span,
            )
        seen.add(parameter)
    arguments.append(
        ArgumentAnalysis(
            word_index=2, kind="list", span=parameters.span, value=tuple(names)
        )
    )
    body = _expect_braced(command.words, 3, "proc_cmd", context)
    _analyze_body(body, context, arguments, 3)


def _handle_return(command, name, context, arguments):
    _expect_count(command.words, 1, 2, "return_cmd", context)
    for index in range(1, len(command.words)):
        arguments.append(
            ArgumentAnalysis(
                word_index=index, kind="word", span=command.words[index].span,
                value=command.words[index],
            )
        )


def _handle_break(command, name, context, arguments):
    _expect_count(command.words, 1, 1, "break_cmd", context)


def _handle_continue(command, name, context, arguments):
    _expect_count(command.words, 1, 1, "continue_cmd", context)


def _handle_global(command, name, context, arguments):
    _expect_count(command.words, 2, None, "global_cmd", context)
    for index in range(1, len(command.words)):
        variable = _expect_identifier(command.words, index, "global_cmd", context)
        arguments.append(
            ArgumentAnalysis(
                word_index=index, kind="identifier", span=command.words[index].span, value=variable
            )
        )


def _handle_catch(command, name, context, arguments):
    _expect_count(command.words, 2, 3, "catch_cmd", context)
    body = _expect_braced(command.words, 1, "catch_cmd", context)
    _analyze_body(body, context, arguments, 1)
    if len(command.words) == 3:
        variable = _expect_identifier(command.words, 2, "catch_cmd", context)
        arguments.append(
            ArgumentAnalysis(
                word_index=2, kind="identifier", span=command.words[2].span, value=variable
            )
        )


def _handle_error(command, name, context, arguments):
    _expect_count(command.words, 2, 2, "error_cmd", context)
    arguments.append(
        ArgumentAnalysis(
            word_index=1, kind="word", span=command.words[1].span, value=command.words[1]
        )
    )


def _handle_list(command, name, context, arguments):
    _expect_count(command.words, 1, None, "list_cmd", context)
    for index in range(1, len(command.words)):
        arguments.append(
            ArgumentAnalysis(
                word_index=index, kind="word", span=command.words[index].span,
                value=command.words[index],
            )
        )


def _handle_llength(command, name, context, arguments):
    _expect_count(command.words, 2, 2, "llength_cmd", context)
    arguments.append(
        ArgumentAnalysis(
            word_index=1, kind="word", span=command.words[1].span, value=command.words[1]
        )
    )


def _handle_lindex(command, name, context, arguments):
    _expect_count(command.words, 3, 3, "lindex_cmd", context)
    for index in (1, 2):
        arguments.append(
            ArgumentAnalysis(
                word_index=index, kind="word", span=command.words[index].span,
                value=command.words[index],
            )
        )


def _handle_lappend(command, name, context, arguments):
    _expect_count(command.words, 2, None, "lappend_cmd", context)
    target = _expect_name(command.words, 1, "lappend_cmd", context)
    arguments.append(
        ArgumentAnalysis(word_index=1, kind="name", span=command.words[1].span, value=target)
    )
    for index in range(2, len(command.words)):
        arguments.append(
            ArgumentAnalysis(
                word_index=index, kind="word", span=command.words[index].span,
                value=command.words[index],
            )
        )


def _handle_lset(command, name, context, arguments):
    _expect_count(command.words, 4, 4, "lset_cmd", context)
    target = _expect_name(command.words, 1, "lset_cmd", context)
    arguments.append(
        ArgumentAnalysis(word_index=1, kind="name", span=command.words[1].span, value=target)
    )
    for index in (2, 3):
        arguments.append(
            ArgumentAnalysis(
                word_index=index, kind="word", span=command.words[index].span,
                value=command.words[index],
            )
        )


def _handle_dict(command, name, context, arguments):
    words = command.words
    _expect_count(words, 2, None, "dict_cmd", context)
    subcommand = literal_text(words[1])
    if subcommand not in DICT_SUBCOMMANDS:
        context.fail(
            "se esperaba uno de 'create', 'get', 'exists' o 'set' tras 'dict'",
            words[1].span,
        )
    if subcommand == "create":
        _expect_count(words, 2, None, "dict_create_cmd", context)
        if (len(words) - 2) % 2 != 0:
            context.fail(
                "dict create exige un número par de argumentos (clave valor)",
                words[0].span,
            )
    elif subcommand in ("get", "exists"):
        _expect_count(words, 4, 4, f"dict_{subcommand}_cmd", context)
    else:  # dict set nombre clave valor
        _expect_count(words, 5, 5, "dict_set_cmd", context)
        _expect_name(words, 2, "dict_set_cmd", context)
    for index in range(1, len(words)):
        arguments.append(
            ArgumentAnalysis(
                word_index=index, kind="word", span=words[index].span, value=words[index]
            )
        )


def _handle_string(command, name, context, arguments):
    words = command.words
    _expect_count(words, 3, None, "string_cmd", context)
    subcommand = literal_text(words[1])
    if subcommand not in STRING_SUBCOMMANDS:
        context.fail(
            "se esperaba 'length', 'tolower', 'toupper' o 'compare' tras 'string'",
            words[1].span,
        )
    if subcommand == "compare":
        _expect_count(words, 4, 4, "string_compare_cmd", context)
    else:
        _expect_count(words, 3, 3, "string_cmd", context)
    for index in range(1, len(words)):
        arguments.append(
            ArgumentAnalysis(
                word_index=index, kind="word", span=words[index].span, value=words[index]
            )
        )


def _handle_split(command, name, context, arguments):
    _expect_count(command.words, 2, 3, "split_cmd", context)
    for index in range(1, len(command.words)):
        arguments.append(
            ArgumentAnalysis(
                word_index=index, kind="word", span=command.words[index].span,
                value=command.words[index],
            )
        )


def _handle_join(command, name, context, arguments):
    _expect_count(command.words, 2, 3, "join_cmd", context)
    for index in range(1, len(command.words)):
        arguments.append(
            ArgumentAnalysis(
                word_index=index, kind="word", span=command.words[index].span,
                value=command.words[index],
            )
        )


_HANDLERS = {
    "set_cmd": _handle_set,
    "unset_cmd": _handle_unset,
    "incr_cmd": _handle_incr,
    "append_cmd": _handle_append,
    "puts_cmd": _handle_puts,
    "expr_cmd": _handle_expr,
    "if_cmd": _handle_if,
    "while_cmd": _handle_while,
    "for_cmd": _handle_for,
    "foreach_cmd": _handle_foreach,
    "proc_cmd": _handle_proc,
    "return_cmd": _handle_return,
    "break_cmd": _handle_break,
    "continue_cmd": _handle_continue,
    "global_cmd": _handle_global,
    "catch_cmd": _handle_catch,
    "error_cmd": _handle_error,
    "list_cmd": _handle_list,
    "llength_cmd": _handle_llength,
    "lindex_cmd": _handle_lindex,
    "lappend_cmd": _handle_lappend,
    "lset_cmd": _handle_lset,
    "dict_cmd": _handle_dict,
    "string_cmd": _handle_string,
    "split_cmd": _handle_split,
    "join_cmd": _handle_join,
    "call_cmd": _handle_call,
}
