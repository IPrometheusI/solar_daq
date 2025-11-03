#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import board
import adafruit_ina228
from datetime import datetime
import signal
import sys
import os

# ======================== CONFIGURACIÓN HARDWARE ========================
# Configuración de hardware INA228
RSHUNT_OHMS = 0.002   # 2 mΩ
IMAX_AMPS   = 1.5     # 1.5 A máximo
ADDRESSES   = [0x40, 0x41]

# Valores de configuración para máxima precisión
AVG_TARGET   = 1024         # muestras para promediado
CT_TARGET_US = 1052         # microsegundos para conversión
ADC_RANGE    = 1            # 0 = ±163.84mV, 1 = ±40.96mV

# Variables globales
sensors = []
running = True

# ======================== CÓDIGOS ANSI PARA TERMINAL ESTÁTICO ========================
class TerminalControl:
    CLEAR_SCREEN = '\033[2J'
    HOME_CURSOR = '\033[H'
    HIDE_CURSOR = '\033[?25l'
    SHOW_CURSOR = '\033[?25h'
    
    @staticmethod
    def goto(row, col):
        return f'\033[{row};{col}H'
    
    @staticmethod
    def clear_line():
        return '\033[K'

# ======================== FUNCIONES AUXILIARES ========================
def signal_handler(sig, frame):
    """Maneja la señal Ctrl+C para terminar limpiamente"""
    global running
    print(TerminalControl.SHOW_CURSOR, end='')
    print(TerminalControl.CLEAR_SCREEN, end='')
    print(TerminalControl.HOME_CURSOR, end='')
    print("\nDeteniendo monitor de INA228...")
    running = False

def _try_set(prop_name, sensor, preferred, fallback=None):
    """Intenta asignar 'preferred'. Si falla y hay 'fallback', intenta fallback."""
    if not hasattr(sensor, prop_name):
        return False
    try:
        setattr(sensor, prop_name, preferred)
        return True
    except Exception:
        if fallback is not None:
            try:
                setattr(sensor, prop_name, fallback)
                return True
            except Exception:
                pass
    return False

def setup_ina(i2c, address):
    """Configura un sensor INA228 con configuración de alta precisión"""
    try:
        print(f"Configurando INA228 @ 0x{address:02X}...")
        s = adafruit_ina228.INA228(i2c, address=address)
        
        # Rango fino de shunt para 2 mΩ
        _try_set("adc_range", s, ADC_RANGE)
        
        # Calibración recomendada por la librería (ajusta SHUNT_CAL y LSBs)
        s.set_calibration(shunt_res=RSHUNT_OHMS, max_current=IMAX_AMPS)
        print(f"  ✓ Calibración: {RSHUNT_OHMS}Ω, {IMAX_AMPS}A")
        
        # Promediado y tiempos (nuevas versiones aceptan enteros "humanos")
        success_avg = _try_set("averaging_count", s, AVG_TARGET, fallback=7)     # 7 suele ser 1024
        success_bus = _try_set("bus_voltage_conv_time", s, CT_TARGET_US, fallback=5)     # 5 suele ser ~1052us
        success_shunt = _try_set("shunt_voltage_conv_time", s, CT_TARGET_US, fallback=5)
        success_temp = _try_set("temp_conv_time", s, CT_TARGET_US, fallback=5)
        
        # También intentar con nombres alternativos por compatibilidad
        if not success_bus:
            _try_set("conversion_time_bus", s, CT_TARGET_US, fallback=5)
        if not success_shunt:
            _try_set("conversion_time_shunt", s, CT_TARGET_US, fallback=5)
        if not success_temp:
            _try_set("conversion_time_temperature", s, CT_TARGET_US, fallback=5)
        
        # Limpia acumuladores de energía/carga
        if hasattr(s, "reset_accumulators"):
            s.reset_accumulators()
            print("  ✓ Acumuladores reseteados")
        
        # Verificar configuración actual
        actual_avg = getattr(s, 'averaging_count', 'N/A')
        actual_ct = getattr(s, 'bus_voltage_conv_time', getattr(s, 'conversion_time_bus', 'N/A'))
        print(f"  ✓ Configuración final: AVG={actual_avg}, CT={actual_ct}us")
        
        return s
        
    except Exception as e:
        print(f"  ✗ Error configurando INA228 @ 0x{address:02X}: {e}")
        raise

def initialize_hardware():
    """Inicializa todos los sensores INA228"""
    global sensors
    
    print("Inicializando hardware INA228...")
    
    # I2C Setup
    try:
        i2c = board.I2C()  # /dev/i2c-1 en la Pi
        print("✓ Bus I2C inicializado")
    except Exception as e:
        print(f"Error inicializando I2C: {e}")
        return False

    sensors = []
    for addr in ADDRESSES:
        try:
            s = setup_ina(i2c, addr)
            sensors.append((addr, s))
            print(f"✓ INA228 @ 0x{addr:02X} listo")
        except Exception as e:
            print(f"⚠ No se pudo inicializar INA228 @ 0x{addr:02X}: {e}")
            sensors.append((addr, None))

    # Verificar si tenemos al menos un sensor
    active_count = sum(1 for addr, sensor in sensors if sensor is not None)
    if active_count == 0:
        print("✗ No hay sensores INA228 disponibles")
        print("  Revisa cableado e I2C con 'i2cdetect -y 1'")
        return False
    
    print(f"✓ {active_count}/{len(ADDRESSES)} sensores INA228 activos")
    return True

def read_sensor_data(sensor):
    """Lee datos de un sensor INA228 específico"""
    if sensor is None:
        return None
    
    try:
        data = {
            'voltage': sensor.bus_voltage,              # V
            'current': sensor.current,                  # A
            'power': sensor.power,                      # W
            'energy': getattr(sensor, "energy", 0.0),   # J (si está disponible)
            'temperature': getattr(sensor, "die_temperature", float("nan"))  # °C
        }
        return data
    except Exception as e:
        return None

def setup_display():
    """Configura la pantalla inicial estática"""
    print(TerminalControl.CLEAR_SCREEN, end='')
    print(TerminalControl.HOME_CURSOR, end='')
    print(TerminalControl.HIDE_CURSOR, end='')
    
    # Título
    print(TerminalControl.goto(1, 1), end='')
    print("╔═══════════════════════════════════════════════════════════════╗")
    print(TerminalControl.goto(2, 1), end='')
    print("║              MONITOR INA228 - ALTA PRECISIÓN                 ║")
    print(TerminalControl.goto(3, 1), end='')
    print(f"║          Rshunt: {RSHUNT_OHMS}Ω - Imax: {IMAX_AMPS}A - AVG: {AVG_TARGET}                   ║")
    print(TerminalControl.goto(4, 1), end='')
    print("╚═══════════════════════════════════════════════════════════════╝")
    
    # Encabezados para cada sensor
    row = 6
    for addr, sensor in sensors:
        print(TerminalControl.goto(row, 1), end='')
        status = "ACTIVO" if sensor is not None else "ERROR"
        print(f"╔══ INA228 @ 0x{addr:02X} - {status} {'═' * 39}")
        
        print(TerminalControl.goto(row + 1, 1), end='')
        print("║  Voltaje:         V │ Corriente:         A │ Temp:       °C ║")
        print(TerminalControl.goto(row + 2, 1), end='')
        print("║  Potencia:        W │ Energía:           J │               ║")
        print(TerminalControl.goto(row + 3, 1), end='')
        print("╚═══════════════════════════════════════════════════════════════╝")
        
        row += 5
    
    # Línea de estado
    status_row = row + 1
    print(TerminalControl.goto(status_row, 1), end='')
    print("─────────────────────────────────────────────────────────────")
    print(TerminalControl.goto(status_row + 1, 1), end='')
    print("  Estado:")
    print(TerminalControl.goto(status_row + 2, 1), end='')
    print("  Presiona Ctrl+C para detener")

def update_display(measurement_count, error_count):
    """Actualiza los valores en la pantalla estática"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    
    # Calcular posición de estado
    status_row = 6 + len(sensors) * 5 + 1 + 1
    
    # Actualizar timestamp y contador
    print(TerminalControl.goto(status_row + 1, 11), end='')
    print(f"Medición #{measurement_count:05d} - {timestamp} - Errores: {error_count}     ")
    
    # Actualizar datos de cada sensor
    row = 6
    for i, (addr, sensor) in enumerate(sensors):
        data = read_sensor_data(sensor)
        
        if data is not None:
            # Voltaje y Corriente (fila 1)
            print(TerminalControl.goto(row + 1, 13), end='')
            print(f"{data['voltage']:7.4f}", end='')
            
            print(TerminalControl.goto(row + 1, 34), end='')
            print(f"{data['current']:+8.4f}", end='')
            
            # Temperatura
            print(TerminalControl.goto(row + 1, 55), end='')
            if not (data['temperature'] != data['temperature']):  # Check for NaN
                print(f"{data['temperature']:6.1f}", end='')
            else:
                print("  N/A ", end='')
            
            # Potencia y Energía (fila 2)
            print(TerminalControl.goto(row + 2, 13), end='')
            print(f"{data['power']:7.4f}", end='')
            
            print(TerminalControl.goto(row + 2, 34), end='')
            print(f"{data['energy']:9.4f}", end='')
        else:
            # Mostrar ERROR en caso de falla de lectura
            print(TerminalControl.goto(row + 1, 13), end='')
            print("  ERROR ", end='')
            print(TerminalControl.goto(row + 1, 34), end='')
            print("   ERROR  ", end='')
            print(TerminalControl.goto(row + 1, 55), end='')
            print(" ERROR", end='')
            print(TerminalControl.goto(row + 2, 13), end='')
            print("  ERROR ", end='')
            print(TerminalControl.goto(row + 2, 34), end='')
            print("    ERROR   ", end='')
        
        row += 5
    
    # Forzar actualización del terminal
    sys.stdout.flush()

def print_calibration_info():
    """Muestra información de calibración antes de iniciar"""
    print("\n" + "="*65)
    print("           INFORMACIÓN DE CONFIGURACIÓN INA228")
    print("="*65)
    print(f"Resistencia de shunt:     {RSHUNT_OHMS} Ω ({RSHUNT_OHMS*1000:.1f} mΩ)")
    print(f"Corriente máxima:         {IMAX_AMPS} A")
    print(f"Promediado objetivo:      {AVG_TARGET} muestras")
    print(f"Tiempo conversión:        {CT_TARGET_US} μs")
    print(f"Rango ADC:               {'±40.96mV' if ADC_RANGE == 1 else '±163.84mV'}")
    print(f"Direcciones I2C:          {', '.join(f'0x{addr:02X}' for addr in ADDRESSES)}")
    
    print(f"\nEspecificaciones:")
    print(f"  Resolución de corriente: ~{(IMAX_AMPS/32768)*1000:.2f} mA")
    print(f"  Resolución de voltaje:   ~0.195 mV")
    print(f"  Precisión esperada:      ±0.5%")
    print("="*65)

# ======================== FUNCIÓN PRINCIPAL ========================
def main():
    global running
    
    # Configurar manejo de señales
    signal.signal(signal.SIGINT, signal_handler)
    
    # Mostrar información de configuración
    print_calibration_info()
    
    # Inicializar hardware
    if not initialize_hardware():
        print("Error: No se pudo inicializar el hardware INA228")
        return
    
    print("\nPresiona Enter para iniciar el monitor estático...")
    input()
    
    # Configurar pantalla estática
    setup_display()
    
    measurement_count = 0
    error_count = 0
    last_measurement_time = time.time()
    
    try:
        while running:
            current_time = time.time()
            
            # Actualizar cada segundo
            if current_time - last_measurement_time >= 1.0:
                measurement_count += 1
                
                # Contar errores (sensores que no responden)
                current_errors = 0
                for addr, sensor in sensors:
                    if sensor is not None:
                        data = read_sensor_data(sensor)
                        if data is None:
                            current_errors += 1
                
                if current_errors > 0:
                    error_count += 1
                
                # Actualizar pantalla
                update_display(measurement_count, error_count)
                
                last_measurement_time = current_time
            
            # Pequeña pausa para no saturar el CPU
            time.sleep(0.05)
            
    except Exception as e:
        print(TerminalControl.SHOW_CURSOR, end='')
        print(TerminalControl.CLEAR_SCREEN, end='')
        print(TerminalControl.HOME_CURSOR, end='')
        print(f"Error crítico: {e}")
    
    finally:
        # Restaurar terminal
        print(TerminalControl.SHOW_CURSOR, end='')
        print(TerminalControl.CLEAR_SCREEN, end='')
        print(TerminalControl.HOME_CURSOR, end='')
        
        print("╔═══════════════════════════════════════════════╗")
        print("║              MONITOR TERMINADO                ║")
        print("╚═══════════════════════════════════════════════╝")
        print(f"Total de mediciones realizadas: {measurement_count}")
        print(f"Ciclos con errores: {error_count}")
        
        if measurement_count > 0:
            success_rate = ((measurement_count - error_count) / measurement_count) * 100
            print(f"Tasa de éxito: {success_rate:.1f}%")
        
        # Mostrar estadísticas finales por sensor
        active_sensors = [addr for addr, sensor in sensors if sensor is not None]
        if active_sensors:
            print(f"Sensores activos durante la sesión: {', '.join(f'0x{addr:02X}' for addr in active_sensors)}")
        
        print("Programa terminado")

if __name__ == "__main__":
    main()
