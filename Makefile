# MiniTcl · analizador sintáctico
#
# Ciclo de trabajo del proyecto.  `make help` lista estos objetivos.
#
#   make test      corre las 35 pruebas automáticas
#   make demo      demostración en la terminal (sin abrir Jupyter)
#   make build     regenera el cuaderno y los módulos  (BORRA las salidas)
#   make run       ejecuta el cuaderno completo y guarda las impresiones
#   make check     ciclo completo y seguro: build + test + run
#   make clean     borra cachés y salidas del cuaderno
#
# El orden importa: `build` siempre ANTES que `run`, porque regenerar el
# cuaderno borra las impresiones que había guardado.
#
# Comandos de análisis (el texto va entre comillas):
#
#   make tokens TEXTO="set x 1"                tokens del lexer manual
#   make ast    TEXTO="set x 1"                AST del parser descendente
#   make formas TEXTO="if {1} {puts si}"       formas de comando
#   make fuente TEXTO="puts a#b"               el fuente con los límites de token
#   make expr   EXPR="2 + 3 * 4"               tokens + AST de una expresión (SLY)
#   make archivo FILE=ejemplos/a_factorial.tcl   fichero MiniTcl completo
#   make demo   ARCHIVO=ejemplos/a_factorial.tcl   atajo de "archivo"

PYTHON  := python3
NOTEBOOK := MiniTcl_Analizador_Descendente_Recursivo_Guia_Estudiante.ipynb
ARCHIVO  ?=
TEXTO    ?=
EXPR     ?=
FILE     ?=

.PHONY: help test demo tokens ast formas fuente expr archivo pruebas build run check clean

help:
	@echo "MiniTcl · analizador sintáctico — objetivos disponibles:"
	@echo ""
	@echo "  make test                                  corre las 35 pruebas automáticas"
	@echo "  make demo                                  demostración en la terminal"
	@echo "  make build                                 regenera el cuaderno y los módulos"
	@echo "  make run                                   ejecuta el cuaderno y guarda las impresiones"
	@echo "  make check                                 build + test + run (el ciclo completo)"
	@echo "  make clean                                 borra cachés y salidas"
	@echo ""
	@echo "  make tokens TEXTO=\"set x 1\"                 tokens del lexer manual"
	@echo "  make ast    TEXTO=\"set x 1\"                 AST del parser descendente"
	@echo "  make formas TEXTO=\"if {1} {puts si}\"        formas de comando"
	@echo "  make fuente TEXTO=\"puts a#b\"                el fuente con los límites de token"
	@echo "  make expr   EXPR=\"2 + 3 * 4\"                tokens + AST de una expresión"
	@echo "  make archivo FILE=ejemplos/a_factorial.tcl  fichero MiniTcl completo"
	@echo ""
	@echo "  Sin argumentos, 'make demo' y 'make tokens/ast/...' leen el texto"
	@echo "  por la entrada estándar (termina con una línea vacía)."

test:
	$(PYTHON) tests/test_minitcl.py

pruebas: test

demo:
	$(PYTHON) demo.py $(ARCHIVO)

tokens:
	$(PYTHON) demo.py tokens "$(TEXTO)"

ast:
	$(PYTHON) demo.py ast "$(TEXTO)"

formas:
	$(PYTHON) demo.py formas "$(TEXTO)"

fuente:
	$(PYTHON) demo.py fuente "$(TEXTO)"

expr:
	$(PYTHON) demo.py expr "$(EXPR)"

archivo:
	$(PYTHON) demo.py archivo "$(FILE)"

build:
	$(PYTHON) tools/build_notebook.py
	$(PYTHON) tools/export_modules.py

run:
	jupyter nbconvert --execute --to notebook --inplace "$(NOTEBOOK)"

check: build test run

clean:
	rm -rf __pycache__ tests/__pycache__ tools/__pycache__ .ipynb_checkpoints
