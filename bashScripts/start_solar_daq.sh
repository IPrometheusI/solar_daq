#!/bin/bash

# Script wrapper para iniciar el sistema de adquisición de datos solar
# Autor: Sistema Solar DAQ
# Fecha: $(date)

# Configuración de paths
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$PROJECT_ROOT/source"
PYTHON_SCRIPT="$SCRIPT_DIR/implementacion.py"
LOG_FILE="/home/pi/solar_daq.log"

# Detectar entorno virtual disponible
VENV_PATH=""
for candidate in "$PROJECT_ROOT/.venv" "$SCRIPT_DIR/venv"; do
    if [ -f "$candidate/bin/activate" ]; then
        VENV_PATH="$candidate"
        break
    fi
done

# Función de logging
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

log_message "=== INICIANDO SISTEMA SOLAR DAQ ==="

# Verificar que existe el directorio
if [ ! -d "$SCRIPT_DIR" ]; then
    log_message "ERROR: No existe el directorio $SCRIPT_DIR"
    exit 1
fi

# Cambiar al directorio del proyecto
cd "$SCRIPT_DIR" || {
    log_message "ERROR: No se pudo cambiar al directorio $SCRIPT_DIR"
    exit 1
}

log_message "Directorio actual: $(pwd)"

# Verificar que existe el entorno virtual
if [ -z "$VENV_PATH" ]; then
    log_message "ERROR: No se encontró un entorno virtual (.venv o source/venv)"
    exit 1
fi

# Activar entorno virtual
log_message "Activando entorno virtual..."
source "$VENV_PATH/bin/activate" || {
    log_message "ERROR: No se pudo activar el entorno virtual"
    exit 1
}

# Verificar que existe el script Python
if [ ! -f "$PYTHON_SCRIPT" ]; then
    log_message "ERROR: No existe el script $PYTHON_SCRIPT"
    exit 1
fi

# Verificar instalación de dependencias críticas
log_message "Verificando dependencias críticas..."
python3 -c "import RPi.GPIO, adafruit_dht, adafruit_ads1x15, adafruit_ina228" 2>/dev/null || {
    log_message "WARNING: Algunas dependencias podrían no estar instaladas"
}

log_message "Iniciando implementacion.py..."
log_message "PID del proceso: $$"

# Ejecutar el script principal
exec python3 "$PYTHON_SCRIPT"
