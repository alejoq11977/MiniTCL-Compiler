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

PYTHON  := python3
NOTEBOOK := MiniTcl_Analizador_Descendente_Recursivo_Guia_Estudiante.ipynb
ARCHIVO  ?=

.PHONY: help test demo build run check clean

help:
	@echo "MiniTcl · analizador sintáctico — objetivos disponibles:"
	@echo ""
	@echo "  make test                                  corre las 35 pruebas automáticas"
	@echo "  make demo                                  demostración en la terminal"
	@echo "  make demo ARCHIVO=ejemplos/a_factorial.tcl  demo con un fichero MiniTcl"
	@echo "  make build                                 regenera el cuaderno y los módulos"
	@echo "  make run                                   ejecuta el cuaderno y guarda las impresiones"
	@echo "  make check                                 build + test + run (el ciclo completo)"
	@echo "  make clean                                 borra cachés y salidas"

test:
	$(PYTHON) tests/test_minitcl.py

demo:
	$(PYTHON) demo.py $(ARCHIVO)

build:
	$(PYTHON) tools/build_notebook.py
	$(PYTHON) tools/export_modules.py

run:
	jupyter nbconvert --execute --to notebook --inplace "$(NOTEBOOK)"

check: build test run

clean:
	rm -rf __pycache__ tests/__pycache__ tools/__pycache__ .ipynb_checkpoints
