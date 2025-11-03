#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASH_SCRIPTS_DIR="$PROJECT_ROOT/bashScripts"
TARGET_HOME="/home/pi"
VENV_DIR="$PROJECT_ROOT/.venv"
REQUIREMENTS_FILE="$PROJECT_ROOT/requirements.txt"
SERVICE_NAME="solar_daq.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"

info() {
    echo "[INFO] $*"
}

warn() {
    echo "[WARN] $*" >&2
}

error_exit() {
    echo "[ERROR] $*" >&2
    exit 1
}

if [ ! -d "$BASH_SCRIPTS_DIR" ]; then
    error_exit "No se encontró el directorio bashScripts en $PROJECT_ROOT"
fi

if [ ! -f "$REQUIREMENTS_FILE" ]; then
    error_exit "No se encontró requirements.txt en $PROJECT_ROOT"
fi

info "Copiando scripts de bashScripts a $TARGET_HOME"
for script in "$BASH_SCRIPTS_DIR"/*.sh; do
    [ -e "$script" ] || continue
    dest="$TARGET_HOME/$(basename "$script")"
    install -m 755 "$script" "$dest"
    info "Instalado $(basename "$script")"
done

# Copiar archivos .desktop si existen
for desktop_file in "$BASH_SCRIPTS_DIR"/*.desktop; do
    [ -e "$desktop_file" ] || continue
    dest="$TARGET_HOME/$(basename "$desktop_file")"
    install -m 644 "$desktop_file" "$dest"
info "Instalado $(basename "$desktop_file")"

done

info "Preparando entorno virtual en $VENV_DIR"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    info "Entorno virtual creado"
else
    info "Entorno virtual existente reutilizado"
fi

PIP_BIN="$VENV_DIR/bin/pip"
PYTHON_BIN="$VENV_DIR/bin/python"

if [ ! -x "$PIP_BIN" ]; then
    error_exit "pip no disponible en $VENV_DIR"
fi

info "Actualizando pip y setuptools"
"$PIP_BIN" install --upgrade pip setuptools wheel

info "Instalando dependencias desde requirements.txt"
"$PIP_BIN" install -r "$REQUIREMENTS_FILE"

setup_systemd_service() {
    if ! command -v systemctl >/dev/null 2>&1; then
        warn "systemctl no disponible; omitiendo autostart"
        return
    fi

    local sudo_cmd=""
    if [ "$(id -u)" -ne 0 ]; then
        if command -v sudo >/dev/null 2>&1; then
            sudo_cmd="sudo"
        else
            warn "No hay privilegios para crear servicio systemd; ejecuta el script con sudo"
            return
        fi
    fi

    info "Configurando servicio systemd ($SERVICE_NAME)"
    local service_content
    service_content="[Unit]\nDescription=Solar DAQ startup wrapper\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nUser=pi\nWorkingDirectory=$PROJECT_ROOT\nEnvironment=SOLAR_DAQ_ENV_FILE=/home/pi/.config/solar_daq.env\nExecStart=/usr/bin/bash /home/pi/start_solar_daq.sh\nRestart=no\n\n[Install]\nWantedBy=multi-user.target\n"

    if ! echo -e "$service_content" | $sudo_cmd tee "$SERVICE_PATH" >/dev/null; then
        warn "No se pudo escribir $SERVICE_PATH"
        return
    fi

    $sudo_cmd systemctl daemon-reload || warn "daemon-reload falló"
    if $sudo_cmd systemctl enable "$SERVICE_NAME"; then
        info "Servicio habilitado para iniciar al arranque"
    else
        warn "No se pudo habilitar el servicio"
    fi

    if $sudo_cmd systemctl restart "$SERVICE_NAME"; then
        info "Servicio iniciado"
    else
        warn "No se pudo iniciar el servicio; revisa systemctl status $SERVICE_NAME"
    fi
}

setup_systemd_service

info "Configuración completada"
info "Para activar el entorno: source $VENV_DIR/bin/activate"
info "Scripts disponibles en $TARGET_HOME"
