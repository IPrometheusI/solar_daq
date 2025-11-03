#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import RPi.GPIO as GPIO
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from datetime import datetime
import signal
import sys

# ======================== CONFIGURACIÓN GPIO ========================
# Limpiar GPIO antes de configurar
try:
    GPIO.cleanup()
except:
    pass

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# MUX Control Pins para el sensor de irradiancia
MUX_S0 = 17  # LSB
MUX_S1 = 27
MUX_S2 = 22  # MSB

# ======================== CONFIGURACIÓN SENSORES ========================
# Factor de calibración del sensor de irradiancia
IRRADIANCE_CALIBRATION_FACTOR = 1000.0 / 75.0

# Variables globales
ads = None
adc_channels = []
running = True

# ======================== FUNCIONES AUXILIARES ========================
def signal_handler(sig, frame):
    """Maneja la señal Ctrl+C para terminar limpiamente"""
    global running
    print("\n\nDeteniendo monitor de irradiancia...")
    running = False

def initialize_hardware():
    """Inicializa el hardware necesario para medir irradiancia"""
    global ads, adc_channels
    
    print("Inicializando hardware para medición de irradiancia...")
    
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

    # ADS1115 Setup
    max_retries = 3
    for attempt in range(max_retries):
        try:
            ads = ADS.ADS1115(i2c, address=0x48)
            ads.gain = 1
            adc_channels = [
                AnalogIn(ads, ADS.P1)   # A1 -> Z3 (MUX3) para irradiancia
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
        time.sleep(0.1)  # Tiempo de estabilización del MUX (0.1s para irradiancia)
        return True
    except Exception as e:
        print(f"Error configurando canal MUX {channel}: {e}")
        return False

def read_irradiance():
    """Lee el sensor de irradiancia"""
    if ads is None or len(adc_channels) < 1:
        return None, None
    
    try:
        # IRR- (Y4 - canal 4 del MUX)
        if not set_mux_channel(4):
            return None, None
        time.sleep(0.1)  # Tiempo de estabilización del ADS después del cambio de canal
        voltage_minus = adc_channels[0].voltage
        
        # IRR+ (Y5 - canal 5 del MUX)  
        if not set_mux_channel(5):
            return None, None
        time.sleep(0.1)  # Tiempo de estabilización del ADS después del cambio de canal
        voltage_plus = adc_channels[0].voltage
        
        # Calcular diferencial
        irradiance_voltage = abs(voltage_plus - voltage_minus)
        irradiance_voltage_mV = irradiance_voltage * 1000.0
        irradiance_wm2 = irradiance_voltage_mV * IRRADIANCE_CALIBRATION_FACTOR
        
        return irradiance_voltage_mV, irradiance_wm2
        
    except Exception as e:
        print(f"Error leyendo irradiancia: {e}")
        return None, None



def print_measurement(voltage, irradiance, measurement_count):
    """Imprime la medición en pantalla"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    if voltage is not None and irradiance is not None:
        print(f"[{timestamp}] Medición #{measurement_count:04d} - "
              f"Voltaje: {voltage:.3f}mV, Irradiancia: {irradiance:.2f} W/m²")
    else:
        print(f"[{timestamp}] Medición #{measurement_count:04d} - ERROR en lectura")

# ======================== FUNCIÓN PRINCIPAL ========================
def main():
    global running
    
    print("=== MONITOR DE IRRADIANCIA SOLAR ===")
    print("Mediciones cada 2 segundos")
    print("Presiona Ctrl+C para detener\n")
    
    # Configurar manejo de señales
    signal.signal(signal.SIGINT, signal_handler)
    
    # Inicializar hardware
    if not initialize_hardware():
        print("Error: No se pudo inicializar el hardware")
        return
    
    print("=== INICIANDO MEDICIONES ===")
    print("Formato: [Hora] Medición #XXXX - Voltaje: XXX.XXXmV, Irradiancia: XXX.XX W/m²\n")
    
    measurement_count = 0
    last_measurement_time = time.time()
    
    try:
        while running:
            current_time = time.time()
            
            # Medir cada 2 segundos
            if current_time - last_measurement_time >= 2.0:
                measurement_count += 1
                
                # Leer irradiancia
                voltage, irradiance = read_irradiance()
                
                # Mostrar en pantalla
                print_measurement(voltage, irradiance, measurement_count)
                
                last_measurement_time = current_time
            
            # Pequeña pausa para no saturar el CPU
            time.sleep(0.1)
            
    except Exception as e:
        print(f"\nError crítico: {e}")
    
    finally:
        print(f"\n=== FINALIZANDO ===")
        print(f"Total de mediciones realizadas: {measurement_count}")
        
        # Limpiar GPIO
        try:
            GPIO.cleanup()
            print("✓ GPIO limpiado")
        except Exception as e:
            print(f"Error limpiando GPIO: {e}")
        
        print("Monitor terminado correctamente")

if __name__ == "__main__":
    main()