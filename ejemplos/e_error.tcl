# Programa con un error sintáctico: sirve para demostrar el diagnóstico.
# El bloque entre llaves está sin cerrar, así que el lexer avisa de la llave
# que falta indicando dónde se abrió.
puts "Antes del error"
if {1 == 1} {
    puts [expr {2 + 3}]
