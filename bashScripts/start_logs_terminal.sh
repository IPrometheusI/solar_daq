#!/bin/bash

# Script para abrir terminal con logs
# Ubicación: /home/pi/start_logs_terminal.sh

# Esperar un poco más para que el primer terminal se abra primero
sleep 15

# Configuración
LOG_FILE="/home/pi/solar_daq.log"

# Crear archivo de log si no existe
touch "$LOG_FILE"

# Abrir terminal con tail de logs
lxterminal --title="Sistema Solar DAQ - Logs en Tiempo Real" --geometry=100x30+800+0 -e bash -c "
    echo '=== SISTEMA SOLAR DAQ - MONITOR DE LOGS ==='
    echo 'Mostrando logs en tiempo real...'
    echo 'Archivo: $LOG_FILE'
    echo 'Presiona Ctrl+C para detener el seguimiento'
    echo '==========================================='
    echo ''
    tail -f '$LOG_FILE'
"