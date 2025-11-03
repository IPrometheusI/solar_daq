#!/bin/bash

# Script para monitorear implementacion.py desde cualquier terminal
# Ubicación: /home/pi/watch_implementacion.sh

OUTPUT_LOG="/home/pi/implementacion_live_output.log"

echo "=== MONITOR IMPLEMENTACION.PY ==="
echo "Archivo: $OUTPUT_LOG"
echo "Presiona Ctrl+C para salir"
echo "==============================="

# Verificar si el archivo existe
if [ ! -f "$OUTPUT_LOG" ]; then
    echo "⚠️  Archivo de output no existe todavía."
    echo "   Asegúrate de que implementacion.py esté corriendo."
    echo "   Esperando a que aparezca el archivo..."
    
    # Esperar hasta que aparezca el archivo
    while [ ! -f "$OUTPUT_LOG" ]; do
        sleep 2
        echo -n "."
    done
    echo ""
    echo "✅ ¡Archivo encontrado! Mostrando output..."
fi

# Mostrar las últimas 10 líneas primero
echo ""
echo "=== ÚLTIMAS 10 LÍNEAS ==="
tail -n 10 "$OUTPUT_LOG" 2>/dev/null
echo ""
echo "=== OUTPUT EN TIEMPO REAL ==="

# Seguir el archivo en tiempo real
tail -f "$OUTPUT_LOG"
