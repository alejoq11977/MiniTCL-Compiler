"""Pruebas reproducibles del analizador sintáctico de MiniTcl.

El fichero no necesita ``pytest``: basta con ejecutarlo
(``python3 tests/test_minitcl.py``).  Las funciones ``test_*`` también se
pueden recoger con cualquier corredor de pruebas.

Se cubren:

* las comprobaciones del material suministrado (celda 26 del cuaderno),
* el contrato léxico (sección 3),
* la gramática estructural (sección 4) y la matriz de la sección 16,
* la gramática de expresiones de SLY (sección 5),
* la validación de comandos y el reanálisis estático (secciones 6 y 13),
* el lector de listas (sección 7),
* los programas de aceptación de la sección 15).
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from command_analyzer import analyze_command, analyze_minitcl, analyze_script
from expr_lexer import ExprLexer
from expr_parser import ExprParser, parse_minitcl_expr
from list_reader import format_list, parse_list
from model import (
    Binary,
    Command,
    CommandSubstitution,
    Constant,
    Literal,
    ParseError,
    Script,
    Span,
    SubstitutionExpr,
    Token,
    TokenCursor,
    Unary,
    Variable,
    VariableExpr,
    Word,
    cover,
    expr_shape,
)
from script_lexer import show_tokens, tokenize_script
from script_parser import ScriptParser, parse_minitcl, read_substitution




# --- Utilidades --------------------------------------------------------------
def word_modes(script):
    """Lista de listas con el modo y las partes de cada palabra."""
    return [
        [(word.mode, tuple(type(p).__name__ for p in word.parts)) for word in command.words]
        for command in script.commands
    ]


def literal_of(source, command=0, word=1):
    """Texto literal de una palabra del script."""
    return parse_minitcl(source).commands[command].words[word].parts[0].text


def kinds_of(source):
    """Secuencia de tipos de token del lexer manual."""
    return [token.kind for token in tokenize_script(source)]


# --- Material suministrado ---------------------------------------------------
def test_esqueleto_suministrado():
    """Las comprobaciones de la celda 26 del cuaderno siguen siendo válidas."""
    assert ScriptParser([Token("EOF", "", Span(0, 0))]).parse().commands == ()
    trailing = [
        Token("TEXT", "puts", Span(0, 4)),
        Token("WS", " ", Span(4, 5)),
        Token("EOF", "", Span(5, 5)),
    ]
    assert len(ScriptParser(trailing).parse().commands[0].words) == 1
    try:
        ScriptParser(
            [Token("RBRACKET", "]", Span(0, 1)), Token("EOF", "", Span(1, 1))]
        ).parse()
    except ParseError:
        pass
    else:
        raise AssertionError("No se debe aceptar un cierre exterior")


def test_pruebas_del_estudiante():
    """El bloque de la celda 27 con ``RUN_STUDENT_TESTS`` activado."""
    script = parse_minitcl('puts "Hola $nombre"; set x {a b}')
    assert len(script.commands) == 2
    assert len(script.commands[0].words) == 2
    greeting = script.commands[0].words[1]
    assert greeting.mode == "quoted"
    assert [type(p).__name__ for p in greeting.parts] == ["Literal", "Variable"]
    block = script.commands[1].words[2]
    assert block.mode == "braced" and block.parts[0].text == "a b"
    assert expr_shape(parse_minitcl_expr("2 + 3 * 4")) == ("+", 2, ("*", 3, 4))
    assert expr_shape(parse_minitcl_expr("10 - 3 - 2")) == ("-", ("-", 10, 3), 2)
    assert expr_shape(parse_minitcl_expr("2 ** 3 ** 2")) == ("**", 2, ("**", 3, 2))
    assert expr_shape(parse_minitcl_expr("-2 ** 2")) == ("-", ("**", 2, 2))
    assert expr_shape(parse_minitcl_expr("2 ** -3")) == ("**", 2, ("-", 3))


# --- Contrato léxico (sección 3) ----------------------------------------------
def test_lexer_tokens_basicos():
    assert kinds_of("set x 10") == ["TEXT", "WS", "TEXT", "WS", "TEXT", "EOF"]
    assert kinds_of("set x 10; puts hi") == [
        "TEXT", "WS", "TEXT", "WS", "TEXT", "SEP", "WS", "TEXT", "WS", "TEXT", "EOF",
    ]
    assert kinds_of("set x 10\nputs hi") == [
        "TEXT", "WS", "TEXT", "WS", "TEXT", "SEP", "TEXT", "WS", "TEXT", "EOF",
    ]
    # Un salto de línea siempre es SEP, también después de un comentario.
    assert kinds_of("# comentario\nputs hi") == ["SEP", "TEXT", "WS", "TEXT", "EOF"]


def test_show_tokens():
    """La impresión de tokens funciona con las dos familias de tokens."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        show_tokens(tokenize_script("set x 1"))
        show_tokens(list(ExprLexer().tokenize("2 + 3")))
    salida = buffer.getvalue()
    assert "TEXT" in salida and "WS" in salida and "EOF" in salida
    assert "NUMBER" in salida and "PLUS" in salida
    assert "[0:3]" in salida  # la posición del primer token del script


def test_lexer_no_crea_text_vacio():
    tokens = tokenize_script('puts ""')
    assert not [t for t in tokens if t.kind == "TEXT" and t.value == ""]


def test_lexer_hash_solo_al_inicio_de_comando():
    # 'puts a#b' y 'puts #dato' contienen texto, no comentarios.
    assert literal_of("puts a#b") == "a#b"
    assert literal_of("puts #dato") == "#dato"
    # Un comentario produce un script vacío.
    assert parse_minitcl("# comentario").commands == ()
    assert parse_minitcl("# comentario\nputs hi").commands[0].words[0].parts[0].text == "puts"


def test_lexer_escapes():
    assert literal_of(r"puts a\nb") == "a\nb"
    assert literal_of(r"puts a\tb") == "a\tb"
    assert literal_of(r"puts a\\b") == "a\\b"
    assert literal_of(r"puts a\ b") == "a b"
    assert literal_of(r"puts \$x") == "$x"
    assert literal_of(r"puts \[x") == "[x"
    assert literal_of(r"puts \{x") == "{x"
    assert literal_of(r"puts a\;b") == "a;b"
    assert literal_of(r"puts a\#b") == "a#b"
    # Dentro de las llaves no se decodifica nada.
    assert literal_of(r"puts {a\nb}") == r"a\nb"
    # Un escape desconocido es error en este perfil.
    try:
        parse_minitcl(r"puts a\qb")
    except ParseError:
        pass
    else:
        raise AssertionError("un escape desconocido debe ser error")
    # La continuación con barra y salto de línea está fuera del perfil.
    try:
        parse_minitcl("puts a\\\nb")
    except ParseError:
        pass
    else:
        raise AssertionError("la continuación de línea debe rechazarse")


def test_lexer_variables():
    script = parse_minitcl("puts $a(3) ${b} $c")
    words = script.commands[0].words
    assert len(words) == 4
    assert isinstance(words[1].parts[0], Variable)
    assert words[1].parts[0].name == "a" and words[1].parts[0].index == "3"
    assert isinstance(words[2].parts[0], Variable)
    assert words[2].parts[0].name == "b" and words[2].parts[0].index is None
    assert isinstance(words[3].parts[0], Variable) and words[3].parts[0].name == "c"
    # '${x}' desambigua "${x}_fin".
    partes = parse_minitcl('puts "${x}_fin"').commands[0].words[1].parts
    assert [type(p).__name__ for p in partes] == ["Variable", "Literal"]
    assert partes[1].text == "_fin"
    # Un '$' sin nombre válido es error.
    for source in ("puts $", "puts $1", "puts $a()", "puts $a($i)"):
        try:
            parse_minitcl(source)
        except ParseError:
            pass
        else:
            raise AssertionError(f"{source!r} debe ser error léxico")


def test_lexer_balanceo_y_mensajes():
    for source, expected in (
        ("puts {sin cierre", "falta la llave de cierre"),
        ('puts "sin cierre', "falta la comilla de cierre"),
        ("puts [set x 1", "falta el corchete de cierre"),
    ):
        try:
            parse_minitcl(source)
        except ParseError as error:
            assert expected in error.message, error.message
        else:
            raise AssertionError(f"{source!r} debe ser error")


# --- Gramática estructural (sección 4) ----------------------------------------
def test_modos_de_palabra():
    assert word_modes(parse_minitcl('puts ""')) == [
        [("bare", ("Literal",)), ("quoted", ())]
    ]
    assert word_modes(parse_minitcl("puts {}")) == [
        [("bare", ("Literal",)), ("braced", ("Literal",))]
    ]
    assert word_modes(parse_minitcl("set x hola_${nombre}_fin")) == [
        [
            ("bare", ("Literal",)),
            ("bare", ("Literal",)),
            ("bare", ("Literal", "Variable", "Literal")),
        ]
    ]


def test_espacios_significativos():
    # El primer comando tiene dos palabras, el segundo tres y el tercero tres.
    assert [len(command.words) for command in parse_minitcl(
        'puts "Hola $nombre: [expr {2 + 3}]"\nset dato {una palabra con espacios}\n'
        "set ruta prefijo_${nombre}_fin"
    ).commands] == [2, 3, 3]


def test_sustituciones_anidadas():
    script = parse_minitcl("puts [set x 1; set x]")
    substitution = script.commands[0].words[1].parts[0]
    assert isinstance(substitution, CommandSubstitution)
    assert len(substitution.script.commands) == 2
    nested = parse_minitcl("puts [list [set x] y]")
    assert isinstance(nested.commands[0].words[1].parts[0], CommandSubstitution)


def test_texto_entre_llaves_es_dato():
    script = parse_minitcl("puts {a {b} c}")
    assert script.commands[0].words[1].parts[0].text == "a {b} c"
    assert script.commands[0].words[1].mode == "braced"
    # Las barras se conservan dentro de las llaves.
    assert literal_of(r"puts {a\{b\}c}") == r"a\{b\}c"
    # Un bloque entre llaves no es un condicional.
    script = parse_minitcl("puts {if mal formado}")
    assert script.commands[0].words[1].mode == "braced"


def test_texto_adyacente_tras_palabra_agrupada():
    for source in ('puts {a}b', 'puts "a"b'):
        try:
            parse_minitcl(source)
        except ParseError:
            pass
        else:
            raise AssertionError(f"{source!r} debe ser error")


def test_cierre_fuera_de_contexto():
    try:
        parse_minitcl("puts ]")
    except ParseError:
        pass
    else:
        raise AssertionError("un cierre exterior debe ser error")


def test_comentario_no_separa_comandos():
    # El salto de línea del comentario sigue separando comandos.
    script = parse_minitcl("puts a # comentario\nputs b")
    assert len(script.commands) == 2


# --- Matriz de la sección 16 --------------------------------------------------
def test_matriz_16_positivos():
    assert parse_minitcl('puts ""').commands[0].words[1].mode == "quoted"
    assert parse_minitcl("puts {}").commands[0].words[1].mode == "braced"
    assert len(parse_minitcl("set x hola_${nombre}_fin").commands[0].words) == 3
    assert len(parse_minitcl("puts [set x 1; set x]").commands[0].words[1].parts[0].script.commands) == 2
    assert literal_of("puts {a {b} c}") == "a {b} c"
    assert literal_of(r"puts {a\{b\}c}") == r"a\{b\}c"
    assert literal_of("puts a#b") == "a#b"
    assert literal_of("puts #dato") == "#dato"
    assert parse_minitcl("# comentario").commands == ()
    assert literal_of('puts "a; b"') == "a; b"
    variable = parse_minitcl("puts $a(3)").commands[0].words[1].parts[0]
    assert isinstance(variable, Variable) and variable.index == "3"


def test_matriz_16_negativos():
    casos = [
        "puts $a($i)",
        "puts {sin cierre",
        'puts "sin cierre',
        "puts [set x 1",
        "puts {a}b",
        'puts "a"b',
        "puts ]",
    ]
    for source in casos:
        try:
            parse_minitcl(source)
        except ParseError:
            pass
        else:
            raise AssertionError(f"{source!r} debe ser un ParseError")


def test_matriz_16_en_la_etapa_apropiada():
    # Errores de aridad: el AST estructural es válido, el validador no.
    script = parse_minitcl("set x 1 2")
    assert len(script.commands[0].words) == 4
    try:
        analyze_script(script, "set x 1 2")
    except ParseError:
        pass
    else:
        raise AssertionError("set x 1 2 debe fallar en la validación")
    # 'if {1} {puts si} else' es estructuralmente válido.
    script = parse_minitcl("if {1} {puts si} else")
    try:
        analyze_script(script, "if {1} {puts si} else")
    except ParseError:
        pass
    else:
        raise AssertionError("falta el cuerpo de else debe fallar en la validación")
    # 'expr {2 + }' es un script válido con una expresión inválida.
    try:
        analyze_minitcl("expr {2 + }")
    except ParseError:
        pass
    else:
        raise AssertionError("expr {2 + } debe fallar al analizar la expresión")
    # 'puts {if mal formado}' es válido: ese argumento es texto.
    analyze_minitcl("puts {if mal formado}")


# --- Expresiones con SLY (sección 5) -----------------------------------------
def test_gramatica_sly_sin_conflictos():
    table = ExprParser._lrtable
    assert len(table.sr_conflicts) == 0, table.sr_conflicts
    assert len(table.rr_conflicts) == 0, table.rr_conflicts


def test_formas_de_expresion():
    esperados = [
        ("2 + 3 * 4", ("+", 2, ("*", 3, 4))),
        ("10 - 3 - 2", ("-", ("-", 10, 3), 2)),
        ("2 ** 3 ** 2", ("**", 2, ("**", 3, 2))),
        ("-2 ** 2", ("-", ("**", 2, 2))),
        ("2 ** -3", ("**", 2, ("-", 3))),
        ("8 / 2 * 3", ("*", ("/", 8, 2), 3)),
        ("1 < 2 == 1", ("==", ("<", 1, 2), 1)),
        ("!0", ("!", 0)),
        ("true", True),
        ("$x != 0 && 10 / $x > 1", ("&&", ("!=", ("var", "x", None), 0), (">", ("/", 10, ("var", "x", None)), 1))),
    ]
    for source, esperado in esperados:
        obtenido = expr_shape(parse_minitcl_expr(source))
        assert obtenido == esperado, f"{source}: {obtenido} != {esperado}"


def test_expresion_rechaza_residuos():
    for source in ("2 3", "2 +", "(1", "", "2 @ 3"):
        try:
            parse_minitcl_expr(source)
        except ParseError:
            pass
        else:
            raise AssertionError(f"{source!r} debe ser un ParseError")


def test_sustitucion_en_expresion():
    expression = parse_minitcl_expr("[doble 2]")
    assert isinstance(expression, SubstitutionExpr)
    assert len(expression.script.commands) == 1
    # Una sustitución dentro de una expresión conserva el cortocircuito: el
    # AST no consulta ningún valor.
    expression = parse_minitcl_expr("0 && [error inesperado]")
    assert expr_shape(expression) == ("&&", 0, ("subst", (2,)))


# --- Validación de comandos (sección 6) --------------------------------------
def test_formas_de_comando():
    analysis = analyze_minitcl("set x 1")
    assert analysis.commands[0].form == "set_cmd"
    assert analysis.commands[0].arguments[0].kind == "name"
    assert analysis.commands[0].arguments[0].value == "x"
    assert analyze_minitcl("puts hi").commands[0].form == "puts_cmd"
    assert analyze_minitcl("puts -nonewline hi").commands[0].form == "puts_cmd"
    assert analyze_minitcl("miProc 1 2").commands[0].form == "call_cmd"


def test_nombre_calculado_fuera_de_perfil():
    # 'set accion puts; $accion hola' es estructuralmente válido...
    script = parse_minitcl("set accion puts; $accion hola")
    assert len(script.commands) == 2
    # ... pero el validador lo rechaza.
    try:
        analyze_script(script, "set accion puts; $accion hola")
    except ParseError:
        pass
    else:
        raise AssertionError("un nombre de comando calculado está fuera del perfil")


def test_parametros_duplicados():
    try:
        analyze_minitcl("proc f {x x} {return $x}")
    except ParseError as error:
        assert "duplicado" in error.message
    else:
        raise AssertionError("los parámetros duplicados deben ser error")


def test_incorporados_no_redefinibles():
    try:
        analyze_minitcl("proc set {x} {return $x}")
    except ParseError as error:
        assert "redefinir" in error.message
    else:
        raise AssertionError("no se puede redefinir un incorporado")


def test_cuerpo_estatico_incorrecto_se_reporta():
    # Aunque la rama no se tome, el error de sintaxis del cuerpo se reporta.
    try:
        analyze_minitcl("if {1} {puts sin cierre")
    except ParseError:
        pass
    else:
        raise AssertionError("el cuerpo estático debe analizarse")


# --- Lector de listas (sección 7) ---------------------------------------------
def test_contrato_de_listas():
    valores = [["a", "b"], [], [""], ["a b"], ["{x}"], ['say "hi"'], ["a;b"], ["a\\b"]]
    for value in valores:
        assert parse_list(format_list(value)) == value, value


def test_lista_no_es_script():
    # '$x', '[cmd]' y ';' son datos dentro de una lista.
    assert parse_list("$x [cmd] ; y") == ["$x", "[cmd]", ";", "y"]


def test_lector_de_listas_rechaza_agrupaciones_pegadas():
    for source in ("{a}b", '"a"b'):
        try:
            parse_list(source)
        except ParseError:
            pass
        else:
            raise AssertionError(f"{source!r} debe ser error")


# --- Programas de aceptación (sección 15) ------------------------------------
PROGRAMAS = {
    "A": """proc factorial {n} {
    if {$n <= 1} {return 1}
    return [expr {$n * [factorial [expr {$n - 1}]]}]
}
puts [factorial 6]""",
    "B": """set datos [list 4 8 15 16 23 42]
set suma 0
foreach dato $datos {
    set suma [expr {$suma + $dato}]
}
set promedio [expr {$suma / [llength $datos]}]
puts "Promedio: $promedio\"""",
    "C": """set conteo [dict create]
foreach palabra [split {sol luna sol mar luna sol}] {
    if {[dict exists $conteo $palabra]} {
        dict set conteo $palabra [expr {[dict get $conteo $palabra] + 1}]
    } else {
        dict set conteo $palabra 1
    }
}
puts [dict get $conteo sol]""",
    "D": """set tabla(3) 9
for {set i 0} {$i < 5} {incr i} {
    if {$i == 2} {continue}
    puts [expr {$i * $i}]
}
set codigo [catch {expr {10 / 0}} mensaje]
puts "$codigo: $mensaje"
puts $tabla(3)""",
}


def test_programas_de_aceptacion():
    for clave, fuente in PROGRAMAS.items():
        analysis = analyze_minitcl(fuente, f"programa_{clave}")
        assert analysis.commands, clave


def test_analisis_estatico_del_programa_a():
    """En el programa A se reanalizan el cuerpo, la condición y las expresiones."""
    analysis = analyze_minitcl(PROGRAMAS["A"], "programa_A")
    procedure = analysis.commands[0]
    assert procedure.form == "proc_cmd"
    cuerpo = [a for a in procedure.arguments if a.kind == "script"]
    assert cuerpo, "el cuerpo del procedimiento debe analizarse como script"
    assert procedure.bodies, "el cuerpo se valida como script"
    # Dentro del cuerpo, el 'if' tiene su condición analizada como expresión.
    inner_if = procedure.bodies[0].commands[0]
    assert inner_if.form == "if_cmd"
    assert [a for a in inner_if.arguments if a.kind == "expr"], "la condición se analiza"
    assert inner_if.bodies, "el cuerpo del 'if' se valida"


# --- Diagnósticos (sección 17) -----------------------------------------------
def test_diagnostico_con_linea_y_columna():
    try:
        parse_minitcl("puts hola\nputs {sin cierre")
    except ParseError as error:
        assert error.line == 2, error.line
        assert error.column == 6, error.column
        assert "sin cierre" in str(error)
        assert "^" in str(error)
    else:
        raise AssertionError("se esperaba un ParseError")


def test_cover():
    span = cover(Span(0, 3, "f"), Span(7, 9, "f"))
    assert span == Span(0, 9, "f")


# --- Ejecutor ----------------------------------------------------------------
def main() -> int:
    pruebas = [
        (nombre, funcion)
        for nombre, funcion in sorted(globals().items())
        if nombre.startswith("test_") and callable(funcion)
    ]
    fallos = 0
    for nombre, funcion in pruebas:
        try:
            funcion()
        except Exception as error:  # noqa: BLE001 - se informa de cada fallo
            fallos += 1
            print(f"FALLO  {nombre}: {type(error).__name__}: {error}")
        else:
            print(f"OK     {nombre}")
    print(f"\n{len(pruebas) - fallos}/{len(pruebas)} pruebas correctas.")
    return 1 if fallos else 0


# En el cuaderno la celda ejecuta las pruebas al final; como módulo, el
# fichero se ejecuta con "python3 tests/test_minitcl.py" (véase el sufijo de
# exportación en tools/layout.py).
if __name__ == "__main__" and "get_ipython" in globals():
    main()


if __name__ == "__main__":
    raise SystemExit(main())
