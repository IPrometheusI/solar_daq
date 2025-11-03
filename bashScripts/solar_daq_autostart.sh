#!/bin/bash

# Script principal de autostart para Sistema Solar DAQ
# Ubicación: /home/pi/solar_daq_autostart.sh

# Logging
LOG_FILE="/home/pi/autostart_solar_daq.log"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

log_message "=== INICIANDO AUTOSTART SOLAR DAQ ==="

# Verificar que estamos en el usuario correcto
if [ "$(whoami)" != "pi" ]; then
    log_message "WARNING: Ejecutándose como usuario $(whoami), debería ser 'pi'"
fi

# Esperar a que el escritorio esté completamente cargado
log_message "Esperando carga completa del escritorio..."
for i in {1..30}; do
    if [ -n "$DISPLAY" ] && xset q &>/dev/null; then
        log_message "Escritorio listo después de ${i} segundos"
        break
    fi
    sleep 1
done

# Verificar que estamos en entorno gráfico
if [ -z "$DISPLAY" ]; then
    log_message "ERROR: No hay entorno gráfico disponible"
    exit 1
fi

if ! xset q &>/dev/null; then
    log_message "ERROR: No se puede conectar al servidor X"
    exit 1
fi

log_message "Entorno gráfico detectado: $DISPLAY"

# Verificar que existen los scripts necesarios
SCRIPT1="/home/pi/start_implementacion_terminal.sh"
SCRIPT2="/home/pi/start_logs_terminal.sh"

if [ ! -f "$SCRIPT1" ]; then
    log_message "ERROR: No existe $SCRIPT1"
    exit 1
fi

if [ ! -f "$SCRIPT2" ]; then
    log_message "ERROR: No existe $SCRIPT2"
    exit 1
fi

# Verificar que tienen permisos de ejecución
if [ ! -x "$SCRIPT1" ]; then
    log_message "Corrigiendo permisos de $SCRIPT1"
    chmod +x "$SCRIPT1"
fi

if [ ! -x "$SCRIPT2" ]; then
    log_message "Corrigiendo permisos de $SCRIPT2"
    chmod +x "$SCRIPT2"
fi

# Abrir terminal 1: Implementacion.py
log_message "Abriendo terminal principal (implementacion.py)..."
"$SCRIPT1" &
TERMINAL1_PID=$!

# Esperar un poco antes de abrir la segunda terminal
sleep 5

# Abrir terminal 2: Logs
log_message "Abriendo terminal de logs..."
"$SCRIPT2" &
TERMINAL2_PID=$!

log_message "Terminales iniciadas:"
log_message "  - Terminal implementacion PID: $TERMINAL1_PID"
log_message "  - Terminal logs PID: $TERMINAL2_PID"

log_message "=== AUTOSTART COMPLETADO ==="

# Función para verificar si un proceso está corriendo
is_running() {
    kill -0 "$1" 2>/dev/null
}

# Mantener el script corriendo para monitorear
monitor_count=0
while true; do
    sleep 60
    monitor_count=$((monitor_count + 1))
    
    # Verificar si las terminales siguen activas cada 5 minutos
    if [ $((monitor_count % 5)) -eq 0 ]; then
        if ! is_running $TERMINAL1_PID; then
            log_message "WARNING: Terminal principal cerrada (PID: $TERMINAL1_PID)"
        fi
        if ! is_running $TERMINAL2_PID; then
            log_message "WARNING: Terminal de logs cerrada (PID: $TERMINAL2_PID)"
        fi
        log_message "Monitor check #$monitor_count - Sistema funcionando"
    fi
done