#!/bin/bash

# Helpers compartidos para resolver la ruta real del repositorio, incluso
# cuando los scripts son copiados a /home/pi por setup_repo.sh.

is_solar_daq_root() {
    local candidate="$1"
    [ -n "$candidate" ] \
        && [ -d "$candidate/source" ] \
        && [ -f "$candidate/source/implementacion.py" ] \
        && [ -f "$candidate/requirements.txt" ]
}

resolve_solar_daq_root() {
    local candidate=""
    local caller_script=""

    if [ -n "${SOLAR_DAQ_PROJECT_ROOT:-}" ] && is_solar_daq_root "$SOLAR_DAQ_PROJECT_ROOT"; then
        printf '%s\n' "$SOLAR_DAQ_PROJECT_ROOT"
        return 0
    fi

    if [ -r "/home/pi/.config/solar_daq_project_root" ]; then
        candidate="$(head -n 1 /home/pi/.config/solar_daq_project_root)"
        if is_solar_daq_root "$candidate"; then
            printf '%s\n' "$candidate"
            return 0
        fi
    fi

    if is_solar_daq_root "$PWD"; then
        printf '%s\n' "$PWD"
        return 0
    fi

    caller_script="${BASH_SOURCE[1]:-${BASH_SOURCE[0]}}"
    candidate="$(cd "$(dirname "$caller_script")/.." && pwd)"
    if is_solar_daq_root "$candidate"; then
        printf '%s\n' "$candidate"
        return 0
    fi

    for candidate in "/home/pi/Desktop/solar_daq" "/home/pi/solar_daq"; do
        if is_solar_daq_root "$candidate"; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    return 1
}
