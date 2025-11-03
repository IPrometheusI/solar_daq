#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import math
import RPi.GPIO as GPIO
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_dht
from datetime import datetime
import signal
import sys
import os

# ======================== CONFIGURACIÓN GPIO ========================
# Limpiar GPIO antes de configurar
try:
    GPIO.cleanup()
except:
    pass

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# MUX Control Pins
MUX_S0 = 17  # LSB
MUX_S1 = 27
MUX_S2 = 22  # MSB

# DHT22 Pin
DHT22_PIN = 5

# ======================== CONFIGURACIÓN SENSORES MEJORADA ========================
# VCC del divisor de voltaje medido con precisión
VCC = 3.294  # Voltaje real del sistema

# Resistencias de referencia individuales para cada termistor (en Ohms)
THERMISTOR_REF_RESISTANCES = {
    'T0':  10030,  # 10.03kΩ
    'T1':  10050,  # 10.05kΩ
    'T2':  10000,  # 10.00kΩ
    'T3':   9990,  #  9.99kΩ
    'T4':  10000,  # 10.00kΩ
    'T5':  10020,  # 10.02kΩ
    'T6':  10030,  # 10.03kΩ
    'T7':   9990,  #  9.99kΩ
    'T8':  10000,  # 10.00kΩ
    'T9':  10020,  # 10.02kΩ
    'T10':  9980,  #  9.98kΩ
    'T11':  9980,  #  9.98kΩ
    'T12':  9970,  #  9.97kΩ
    'T13': 10030,  # 10.03kΩ
    'T14': 10000,  # 10.00kΩ
    'T15':  9980,  #  9.98kΩ
    'T16': 10010,  # 10.01kΩ
    'T17':  9980,  #  9.98kΩ
    'T18': 10010,  # 10.01kΩ
    'T19': 10000   # 10.00kΩ
}

# Constantes para ecuación Beta
B = 3435.0
T0 = 298.15

# Variables globales
ads = None
adc_channels = []
dhtDevice = None
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
    print("\nDeteniendo monitor de termistores...")
    running = False

def initialize_hardware():
    """Inicializa el hardware necesario"""
    global ads, adc_channels, dhtDevice
    
    print("Inicializando hardware...")
    
    # GPIO Setup para MUX
    try:
        GPIO.setup([MUX_S0, MUX_S1, MUX_S2], GPIO.OUT)
        print("✓ GPIO para MUX configurado")
    except Exception as e:
        print(f"Error configurando GPIO para MUX: {e}")
        return False

    # I2C Setup
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        print("✓ Bus I2C inicializado")
    except Exception as e:
        print(f"Error inicializando I2C: {e}")
        return False

    # DHT22 Setup
    try:
        dhtDevice = adafruit_dht.DHT22(board.D5, use_pulseio=False)
        print("✓ DHT22 inicializado correctamente")
    except Exception as e:
        print(f"Warning: Error inicializando DHT22: {e}")
        dhtDevice = None

    # ADS1115 Setup
    max_retries = 3
    for attempt in range(max_retries):
        try:
            ads = ADS.ADS1115(i2c, address=0x48)
            ads.gain = 1
            adc_channels = [
                AnalogIn(ads, ADS.P3),  # A3 -> Z1 (MUX1) -> T0-T7
                AnalogIn(ads, ADS.P2),  # A2 -> Z2 (MUX2) -> T8-T15
                AnalogIn(ads, ADS.P1),  # A1 -> Z3 (MUX3) -> T16-T19
            ]
            print("✓ ADS1115 inicializado correctamente")
            return True
        except Exception as e:
            print(f"Intento {attempt + 1}/{max_retries} - Error inicializando ADS1115: {e}")
            if attempt == max_retries - 1:
                print("No se pudo inicializar ADS1115")
                return False
            time.sleep(2)
    
    return False

def set_mux_channel(channel):
    """Configura el canal del multiplexor (0-7)"""
    try:
        GPIO.output(MUX_S0, channel & 0x01)
        GPIO.output(MUX_S1, (channel >> 1) & 0x01)
        GPIO.output(MUX_S2, (channel >> 2) & 0x01)
        time.sleep(0.01)  # Tiempo de estabilización
        return True
    except Exception as e:
        return False

def calculate_resistance(voltage, thermistor_id, vcc=VCC):
    """Calcula resistencia del termistor usando resistencia de referencia específica"""
    if voltage <= 0 or voltage >= vcc:
        return float('inf')
    
    # Obtener resistencia de referencia específica para este termistor
    r_ref = THERMISTOR_REF_RESISTANCES.get(thermistor_id, 10000)  # fallback a 10kΩ
    
    return r_ref * voltage / (vcc - voltage)

def calculate_temperature(resistance, thermistor_id):
    """Calcula temperatura usando Steinhart-Hart Simplificado"""
    if resistance <= 0 or math.isinf(resistance):
        return float('nan')
    
    try:
        # Usar la resistencia de referencia específica de cada termistor como R0
        R0 = THERMISTOR_REF_RESISTANCES.get(thermistor_id, 10000.0)  # fallback a 10kΩ
        
        T_kelvin = 1 / ((1/T0) + (1/B) * math.log(resistance / R0))
        return T_kelvin - 273.15
    except:
        return float('nan')

def read_all_thermistors():
    """Lee todos los termistores T0-T19"""
    temperatures = {}
    
    if ads is None or len(adc_channels) < 3:
        return temperatures
    
    try:
        # MUX1: T0-T7 (Z1 -> A3)
        for ch in range(8):
            thermistor_id = f"T{ch}"
            if set_mux_channel(ch):
                try:
                    voltage = adc_channels[0].voltage
                    if voltage is not None:
                        resistance = calculate_resistance(voltage, thermistor_id)
                        temp = calculate_temperature(resistance, thermistor_id)
                        temperatures[thermistor_id] = temp
                    else:
                        temperatures[thermistor_id] = float('nan')
                except:
                    temperatures[thermistor_id] = float('nan')
            else:
                temperatures[thermistor_id] = float('nan')
        
        # MUX2: T8-T15 (Z2 -> A2)
        for ch in range(8):
            thermistor_id = f"T{ch+8}"
            if set_mux_channel(ch):
                try:
                    voltage = adc_channels[1].voltage
                    if voltage is not None:
                        resistance = calculate_resistance(voltage, thermistor_id)
                        temp = calculate_temperature(resistance, thermistor_id)
                        temperatures[thermistor_id] = temp
                    else:
                        temperatures[thermistor_id] = float('nan')
                except:
                    temperatures[thermistor_id] = float('nan')
            else:
                temperatures[thermistor_id] = float('nan')
        
        # MUX3: T16-T19 (Z3 -> A1)
        for ch in range(4):
            thermistor_id = f"T{ch+16}"
            if set_mux_channel(ch):
                try:
                    voltage = adc_channels[2].voltage
                    if voltage is not None:
                        resistance = calculate_resistance(voltage, thermistor_id)
                        temp = calculate_temperature(resistance, thermistor_id)
                        temperatures[thermistor_id] = temp
                    else:
                        temperatures[thermistor_id] = float('nan')
                except:
                    temperatures[thermistor_id] = float('nan')
            else:
                temperatures[thermistor_id] = float('nan')
    
    except Exception as e:
        pass
    
    return temperatures

def read_dht22():
    """Lee temperatura y humedad del DHT22"""
    if dhtDevice is None:
        return None, None
    
    try:
        temp = dhtDevice.temperature
        humidity = dhtDevice.humidity
        return temp, humidity
    except RuntimeError as e:
        return None, None
    except Exception as e:
        return None, None

def setup_display():
    """Configura la pantalla inicial"""
    print(TerminalControl.CLEAR_SCREEN, end='')
    print(TerminalControl.HOME_CURSOR, end='')
    print(TerminalControl.HIDE_CURSOR, end='')
    
    # Título
    print(TerminalControl.goto(1, 1), end='')
    print("╔═══════════════════════════════════════════════════════════════╗")
    print(TerminalControl.goto(2, 1), end='')
    print("║       MONITOR DE TERMISTORES T0-T19 + DHT22 (ALTA PRECISIÓN) ║")
    print(TerminalControl.goto(3, 1), end='')
    print("║               Actualización cada segundo - VCC: 3.294V       ║")
    print(TerminalControl.goto(4, 1), end='')
    print("╚═══════════════════════════════════════════════════════════════╝")
    
    # Encabezados de columnas para termistores
    print(TerminalControl.goto(6, 1), end='')
    print("  SENSOR    TEMPERATURA       SENSOR    TEMPERATURA")
    print(TerminalControl.goto(7, 1), end='')
    print("─────────────────────────────────────────────────────────────")
    
    # Configurar líneas para cada termistor (T0-T19 en dos columnas)
    for i in range(10):  # 10 filas para 20 sensores
        row = 8 + i
        print(TerminalControl.goto(row, 1), end='')
        r_ref_left = THERMISTOR_REF_RESISTANCES[f'T{i}']
        r_ref_right = THERMISTOR_REF_RESISTANCES[f'T{i+10}']
        print(f"    T{i:02d}                         T{i+10:02d}                ")
    
    # Sección DHT22
    print(TerminalControl.goto(19, 1), end='')
    print("─────────────────────────────────────────────────────────────")
    print(TerminalControl.goto(20, 1), end='')
    print("  DHT22 - Temperatura:                Humedad:")
    print(TerminalControl.goto(21, 1), end='')
    print("─────────────────────────────────────────────────────────────")
    
    # Línea de estado
    print(TerminalControl.goto(22, 1), end='')
    print("  Estado:")
    print(TerminalControl.goto(23, 1), end='')
    print("  Presiona Ctrl+C para detener")
    print(TerminalControl.goto(24, 1), end='')
    print("  Resistencias individuales calibradas por termistor")

def update_display(temperatures, measurement_count, errors, dht_temp, dht_humidity):
    """Actualiza los valores en la pantalla estática"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    
    # Actualizar timestamp y contador
    print(TerminalControl.goto(22, 11), end='')
    print(f"Medición #{measurement_count:05d} - {timestamp} - Errores: {errors}     ")
    
    # Actualizar temperaturas (T0-T19 en dos columnas)
    for i in range(10):
        row = 8 + i
        
        # Columna izquierda (T0-T9)
        sensor_left = f"T{i}"
        temp_left = temperatures.get(sensor_left, float('nan'))
        if math.isnan(temp_left):
            temp_str_left = "  ERROR  "
        else:
            temp_str_left = f"{temp_left:7.3f}°C"  # 3 decimales para mostrar precisión
        
        print(TerminalControl.goto(row, 10), end='')
        print(temp_str_left, end='')
        
        # Columna derecha (T10-T19)
        sensor_right = f"T{i+10}"
        temp_right = temperatures.get(sensor_right, float('nan'))
        if math.isnan(temp_right):
            temp_str_right = "  ERROR  "
        else:
            temp_str_right = f"{temp_right:7.3f}°C"  # 3 decimales para mostrar precisión
        
        print(TerminalControl.goto(row, 45), end='')
        print(temp_str_right, end='')
    
    # Actualizar datos DHT22
    print(TerminalControl.goto(20, 24), end='')
    if dht_temp is not None and dht_humidity is not None:
        print(f"{dht_temp:6.2f}°C", end='')
        print(TerminalControl.goto(20, 47), end='')
        print(f"{dht_humidity:6.1f}%", end='')
    else:
        print("  ERROR ", end='')
        print(TerminalControl.goto(20, 47), end='')
        print("  ERROR", end='')
    
    # Forzar actualización del terminal
    sys.stdout.flush()

def print_calibration_info():
    """Muestra información de calibración antes de iniciar"""
    print("\n" + "="*65)
    print("           INFORMACIÓN DE CALIBRACIÓN")
    print("="*65)
    print(f"VCC preciso: {VCC:.3f} V")
    print(f"DHT22 GPIO: {DHT22_PIN} (temperatura y humedad ambiente)")
    print("\nResistencias de referencia por termistor:")
    
    # Mostrar en dos columnas
    for i in range(10):
        left_id = f"T{i}"
        right_id = f"T{i+10}"
        left_res = THERMISTOR_REF_RESISTANCES[left_id]
        right_res = THERMISTOR_REF_RESISTANCES[right_id]
        
        print(f"  {left_id}: {left_res:5d}Ω ({left_res/1000:.2f}kΩ)    "
              f"{right_id}: {right_res:5d}Ω ({right_res/1000:.2f}kΩ)")
    
    # Estadísticas
    resistances = list(THERMISTOR_REF_RESISTANCES.values())
    avg_resistance = sum(resistances) / len(resistances)
    min_resistance = min(resistances)
    max_resistance = max(resistances)
    range_resistance = max_resistance - min_resistance
    
    print(f"\nEstadísticas:")
    print(f"  Promedio: {avg_resistance:.1f}Ω")
    print(f"  Rango:    {min_resistance}Ω - {max_resistance}Ω ({range_resistance}Ω)")
    print(f"  Variación: ±{(range_resistance/avg_resistance)*100/2:.2f}%")
    print("="*65)

# ======================== FUNCIÓN PRINCIPAL ========================
def main():
    global running
    
    # Configurar manejo de señales
    signal.signal(signal.SIGINT, signal_handler)
    
    # Mostrar información de calibración
    print_calibration_info()
    
    # Inicializar hardware
    if not initialize_hardware():
        print("Error: No se pudo inicializar el hardware")
        return
    
    print("\nPresiona Enter para iniciar el monitor estático...")
    input()
    
    # Configurar pantalla estática
    setup_display()
    
    measurement_count = 0
    error_count = 0
    dht_error_count = 0
    last_measurement_time = time.time()
    last_dht_time = time.time()
    
    # Variables para mantener últimos valores válidos del DHT22
    last_valid_dht_temp = None
    last_valid_dht_humidity = None
    
    try:
        while running:
            current_time = time.time()
            
            # Leer sensores cada segundo
            if current_time - last_measurement_time >= 1.0:
                measurement_count += 1
                
                # Leer todos los termistores
                temperatures = read_all_thermistors()
                
                # Leer DHT22 cada 3 segundos
                if current_time - last_dht_time >= 3.0:
                    new_dht_temp, new_dht_humidity = read_dht22()
                    if new_dht_temp is not None and new_dht_humidity is not None:
                        # Actualizar últimos valores válidos
                        last_valid_dht_temp = new_dht_temp
                        last_valid_dht_humidity = new_dht_humidity
                    else:
                        dht_error_count += 1
                    
                    last_dht_time = current_time
                
                # Contar errores de termistores
                current_errors = sum(1 for temp in temperatures.values() if math.isnan(temp))
                if current_errors > 0:
                    error_count += 1
                
                # Actualizar pantalla con últimos valores válidos del DHT22
                update_display(temperatures, measurement_count, error_count,
                             last_valid_dht_temp, last_valid_dht_humidity)
                
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
        print(f"Ciclos con errores de termistores: {error_count}")
        if dht_error_count > 0:
            print(f"Errores de DHT22: {dht_error_count}")
        
        if measurement_count > 0:
            success_rate = ((measurement_count - error_count) / measurement_count) * 100
            print(f"Tasa de éxito termistores: {success_rate:.1f}%")
            if dhtDevice is not None:
                dht_success_rate = ((measurement_count//3 - dht_error_count) / (measurement_count//3)) * 100
                print(f"Tasa de éxito DHT22: {dht_success_rate:.1f}%")
        
        # Limpiar GPIO
        try:
            GPIO.cleanup()
            print("GPIO limpiado correctamente")
        except Exception as e:
            print(f"Error limpiando GPIO: {e}")
        
        print("Programa terminado")

if __name__ == "__main__":
    main()
