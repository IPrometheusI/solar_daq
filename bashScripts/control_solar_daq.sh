#!/bin/bash

# Script de control general para Sistema Solar DAQ
# Ubicación: /home/pi/control_solar_daq.sh

OUTPUT_LOG="/home/pi/implementacion_live_output.log"
AUTOSTART_LOG="/home/pi/autostart_solar_daq.log"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}=== ESTADO DEL SISTEMA SOLAR DAQ ===${NC}"
    echo "Hora actual: $(date '+%Y-%m-%d %H:%M:%S')"
    
    # Verificar proceso Python
    if pgrep -f "implementacion.py" > /dev/null; then
        PID=$(pgrep -f "implementacion.py")
        echo -e "🐍 Python: ${GREEN}✓ Corriendo${NC} (PID: $PID)"
    else
        echo -e "🐍 Python: ${RED}✗ No está corriendo${NC}"
    fi
    
    # Verificar archivo de output
    if [ -f "$OUTPUT_LOG" ]; then
        SIZE=$(du -h "$OUTPUT_LOG" | cut -f1)
        LINES=$(wc -l < "$OUTPUT_LOG")
        echo -e "📄 Output: ${GREEN}✓ Disponible${NC} ($LINES líneas, $SIZE)"
    else
        echo -e "📄 Output: ${RED}✗ No disponible${NC}"
    fi
    
    # Verificar log de autostart
    if [ -f "$AUTOSTART_LOG" ]; then
        echo -e "🚀 Autostart: ${GREEN}✓ Log disponible${NC}"
    else
        echo -e "🚀 Autostart: ${YELLOW}⚠ No hay log${NC}"
    fi
    
    echo ""
}

show_menu() {
    echo -e "${BLUE}OPCIONES:${NC}"
    echo "1) 👀 Ver output en tiempo real (tail -f)"
    echo "2) 📜 Ver últimas 200 líneas"
    echo "3) 🔍 Buscar errores en output"
    echo "4) 📊 Mostrar estadísticas del archivo"
    echo "5) 🚀 Ver log de autostart"
    echo "6) 🔄 Reiniciar sistema"
    echo "7) ⏹️  Detener sistema"
    echo "8) 🔄 Actualizar estado"
    echo "9) ❌ Salir"
    echo ""
    read -p "Selecciona opción (1-9): " choice
}

main() {
    while true; do
        clear
        print_status
        show_menu
        
        case $choice in
            1)
                echo -e "${GREEN}Mostrando output en tiempo real...${NC}"
                echo "Presiona Ctrl+C para volver al menú"
                sleep 2
                if [ -f "$OUTPUT_LOG" ]; then
                    tail -f "$OUTPUT_LOG"
                else
                    echo -e "${RED}Archivo de output no existe${NC}"
                    read -p "Presiona Enter para continuar..."
                fi
                ;;
            2)
                echo -e "${GREEN}Últimas 200 líneas:${NC}"
                if [ -f "$OUTPUT_LOG" ]; then
                    tail -n 200 "$OUTPUT_LOG"
                else
                    echo -e "${RED}Archivo de output no existe${NC}"
                fi
                read -p "Presiona Enter para continuar..."
                ;;
            3)
                echo -e "${GREEN}Buscando errores...${NC}"
                if [ -f "$OUTPUT_LOG" ]; then
                    grep -i "error\|warning\|critical\|exception" "$OUTPUT_LOG" | tail -n 10
                else
                    echo -e "${RED}Archivo de output no existe${NC}"
                fi
                read -p "Presiona Enter para continuar..."
                ;;
            4)
                echo -e "${GREEN}Estadísticas del archivo:${NC}"
                if [ -f "$OUTPUT_LOG" ]; then
                    echo "Archivo: $OUTPUT_LOG"
                    echo "Tamaño: $(du -h "$OUTPUT_LOG" | cut -f1)"
                    echo "Líneas: $(wc -l < "$OUTPUT_LOG")"
                    echo "Última modificación: $(stat -c %y "$OUTPUT_LOG")"
                else
                    echo -e "${RED}Archivo de output no existe${NC}"
                fi
                read -p "Presiona Enter para continuar..."
                ;;
            5)
                echo -e "${GREEN}Log de autostart:${NC}"
                if [ -f "$AUTOSTART_LOG" ]; then
                    tail -n 30 "$AUTOSTART_LOG"
                else
                    echo -e "${RED}Log de autostart no existe${NC}"
                fi
                read -p "Presiona Enter para continuar..."
                ;;
            6)
                echo -e "${YELLOW}Reiniciando sistema...${NC}"
                pkill -f implementacion.py
                sleep 3
                /home/pi/solar_daq_autostart.sh &
                echo "Sistema reiniciado"
                sleep 2
                ;;
            7)
                echo -e "${YELLOW}Deteniendo sistema...${NC}"
                pkill -f implementacion.py
                echo "Sistema detenido"
                sleep 2
                ;;
            8)
                # Solo actualizar estado (el bucle se encarga)
                ;;
            9)
                echo -e "${GREEN}¡Hasta luego!${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}Opción no válida${NC}"
                sleep 1
                ;;
        esac
    done
}

# Manejar Ctrl+C para volver al menú
trap 'echo -e "\n${YELLOW}Volviendo al menú...${NC}"; sleep 1' INT

main
