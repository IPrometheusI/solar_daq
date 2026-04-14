#!/bin/bash

# Script para abrir terminal con implementacion.py
# Ubicación: /home/pi/start_implementacion_terminal.sh

# Esperar un poco para que el escritorio cargue completamente
sleep 10

RESOLVER_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/resolve_project_root.sh"
if [ ! -f "$RESOLVER_SCRIPT" ]; then
    echo "[ERROR] No existe el helper $RESOLVER_SCRIPT" >&2
    exit 1
fi

# shellcheck source=/dev/null
source "$RESOLVER_SCRIPT"

PROJECT_ROOT="$(resolve_solar_daq_root)" || {
    echo "[ERROR] No se pudo resolver la ruta del repositorio solar_daq" >&2
    exit 1
}

SCRIPT_DIR="$PROJECT_ROOT/source"
PYTHON_SCRIPT="$SCRIPT_DIR/implementacion.py"

VENV_PATH=""
for candidate in "$PROJECT_ROOT/.venv" "$SCRIPT_DIR/venv"; do
    if [ -f "$candidate/bin/activate" ]; then
        VENV_PATH="$candidate"
        break
    fi
done

if [ -z "$VENV_PATH" ]; then
    echo "[ERROR] No se encontró un entorno virtual (.venv o source/venv)" >&2
    exit 1
fi

# Abrir terminal con implementacion.py
lxterminal --title="Sistema Solar DAQ - Implementacion" --geometry=100x30+0+0 -e bash -c "
    echo '=== SISTEMA SOLAR DAQ - TERMINAL PRINCIPAL ==='
    echo 'Iniciando en 5 segundos...'
    echo 'Directorio: $SCRIPT_DIR'
    echo 'Script: implementacion.py'
    echo '=============================================='
    sleep 5
    cd '$SCRIPT_DIR'
    source '$VENV_PATH/bin/activate'
    python3 '$PYTHON_SCRIPT'
    echo ''
    echo 'El programa ha terminado. Presiona Enter para cerrar...'
    read
"
