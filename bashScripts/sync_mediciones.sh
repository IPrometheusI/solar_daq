#!/bin/bash

# Configuración
LOCAL_DIR="/home/pi/Desktop/Mediciones"
REMOTE_DIR="gdrive:Mediciones_RaspberryPi"  
LOG_FILE="/home/pi/rclone_sync.log"

# Función de logging
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

log_message "=== INICIANDO SINCRONIZACIÓN ==="

# Verificar conectividad
if ! ping -c 1 8.8.8.8 >/dev/null 2>&1; then
    log_message "ERROR: Sin conexión a Internet"
    exit 1
fi

# Ejecutar el comando que ya te funciona
log_message "Copiando archivos..."
rclone copy "$LOCAL_DIR" "$REMOTE_DIR" --update -v 2>&1 | while read -r line; do
    log_message "$line"
done

if [ $? -eq 0 ]; then
    log_message "✓ Sincronización exitosa"
else
    log_message "✗ Error en sincronización"
fi

log_message "=== SINCRONIZACIÓN FINALIZADA ==="
