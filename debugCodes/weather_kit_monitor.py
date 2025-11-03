#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import math
import RPi.GPIO as GPIO
import board
import busio
import adafruit_dht
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from datetime import datetime
import signal
import sys
import os
import threading
from gpiozero import Button, Device
from gpiozero.pins.pigpio import PiGPIOFactory

# Configurar gpiozero para usar pigpio
Device.pin_factory = PiGPIOFactory()

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

# Sensores digitales
DHT22_PIN = 5
ANEMOMETER_PIN = 23
RAIN_SENSOR_PIN = 6

# ======================== CONFIGURACIÓN SENSORES ========================
# VCC del divisor de voltaje
VCC = 3.294  # Voltaje preciso del sistema

# DHT22
dhtDevice = adafruit_dht.DHT22(board.D5, use_pulseio=False)

# Anemómetro
KPH_PER_COUNT_PER_SEC = 2.4
MEASUREMENT_PERIOD = 1.0
wind_count = 0
last_wind_measurement = time.time()

# Sensor de lluvia
MM_PER_TICK = 0.2794
rain_count = 0
rain_count_total = 0  # Acumulador total

# Direcciones del viento (datasheet)
DIRECTION_TABLE = {
    0.0: 33_000, 22.5: 6_570, 45.0: 8_200, 67.5: 891,
    90.0: 1_000, 112.5: 688, 135.0: 2_200, 157.5: 1_410,
    180.0: 3_900, 202.5: 3_140, 225.0: 16_000, 247.5: 14_120,
    270.0: 120_000, 292.5: 42_120, 315.0: 64_900, 337.5: 21_880,
}

COMPASS = {
    0.0: "N", 22.5: "NNE", 45.0: "NE", 67.5: "ENE",
    90.0: "E", 112.5: "ESE", 135.0: "SE", 157.5: "SSE",
    180.0: "S", 202.5: "SSW", 225.0: "SW", 247.5: "WSW",
    270.0: "W", 292.5: "WNW", 315.0: "NW", 337.5: "NNW"
}

# Variables globales
rain_last_state = 1
rain_poll_thread = None
ads = None
adc_channels = []
anemometer = None
rain_sensor = None
running = True
system_start_time = None

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
    print("\nDeteniendo monitor meteorológico...")
    running = False

def wind_pulse():
    """Callback para pulsos del anemómetro"""
    global wind_count
    wind_count += 1

def rain_pulse():
    """Callback para pulsos del pluviómetro"""
    global rain_count, rain_count_total
    rain_count += 1
    rain_count_total += 1


def start_rain_polling():
    """Inicia un hilo de polling manual para el pluviómetro (1→0 = pulso)."""
    global rain_last_state, rain_poll_thread, running

    # Configurar pin con pull-up
    try:
        GPIO.setup(RAIN_SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    except Exception as e:
        print(f"Error configurando pin de lluvia para polling: {e}")
        return False

    # Leer estado inicial
    try:
        rain_last_state = GPIO.input(RAIN_SENSOR_PIN)
        print(f"✓ Lluvia (GPIO {RAIN_SENSOR_PIN}) listo para polling, estado inicial: {rain_last_state} ({'HIGH' if rain_last_state else 'LOW'})")
    except Exception as e:
        print(f"Error leyendo estado inicial del pin de lluvia: {e}")
        return False

    def _loop():
        global rain_last_state
        while running:
            try:
                current_state = GPIO.input(RAIN_SENSOR_PIN)
                # Detecta flanco descendente (1 → 0)
                if rain_last_state == 1 and current_state == 0:
                    rain_pulse()
                    # Debounce por hardware/agua: 300 ms evita rebotes del balancín
                    time.sleep(0.3)
                rain_last_state = current_state
                time.sleep(0.01)  # 10 ms
            except Exception as e:
                # Evitar que el hilo muera silenciosamente
                print(f"[RAIN-POLL] Error: {e}")
                time.sleep(0.5)

    rain_poll_thread = threading.Thread(target=_loop, name="RainPolling", daemon=True)
    rain_poll_thread.start()
    print("✓ Hilo de polling de lluvia iniciado")
    return True

def initialize_hardware():
    """Inicializa el hardware meteorológico"""
    global ads, adc_channels, anemometer, rain_sensor, system_start_time
    
    print("Inicializando hardware meteorológico...")
    system_start_time = time.time()
    
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
                AnalogIn(ads, ADS.P3),  # A3 -> Z1 (MUX1)
                AnalogIn(ads, ADS.P2),  # A2 -> Z2 (MUX2)
                AnalogIn(ads, ADS.P1),  # A1 -> Z3 (MUX3)
                AnalogIn(ads, ADS.P0)   # A0 -> Dirección del viento
            ]
            print("✓ ADS1115 inicializado correctamente")
            break
        except Exception as e:
            print(f"Intento {attempt + 1}/{max_retries} - Error inicializando ADS1115: {e}")
            if attempt == max_retries - 1:
                print("No se pudo inicializar ADS1115")
                return False
            time.sleep(2)

    # DHT22 Setup
    try:
        print("✓ DHT22 inicializado correctamente")
    except Exception as e:
        print(f"Warning: Error con DHT22: {e}")

    # Anemómetro Setup
    try:
        anemometer = Button(
            ANEMOMETER_PIN,
            pull_up=True,
            bounce_time=0.01
        )
        anemometer.when_pressed = wind_pulse
        anemometer.when_released = wind_pulse
        print("✓ Anemómetro configurado correctamente")
    except Exception as e:
        print(f"Error configurando anemómetro: {e}")
        anemometer = None

    # Sensor de lluvia (POLLING manual)
    try:
        if not start_rain_polling():
            print("✗ No se pudo iniciar el polling de lluvia")
    except Exception as e:
        print(f"Error iniciando polling de lluvia: {e}")
    
    return True

def set_mux_channel(channel):
    """Configura el canal del multiplexor (0-7)"""
    try:
        GPIO.output(MUX_S0, channel & 0x01)
        GPIO.output(MUX_S1, (channel >> 1) & 0x01)
        GPIO.output(MUX_S2, (channel >> 2) & 0x01)
        time.sleep(0.01)
        return True
    except Exception as e:
        return False

def get_wind_speed():
    """Obtiene velocidad del viento en m/s"""
    global wind_count, last_wind_measurement
    
    current_time = time.time()
    time_elapsed = current_time - last_wind_measurement
    
    if time_elapsed >= MEASUREMENT_PERIOD:
        cps = wind_count / time_elapsed
        wind_ms = cps * (KPH_PER_COUNT_PER_SEC / 3.6)  # Convertir km/h a m/s
        
        wind_count = 0
        last_wind_measurement = current_time
        
        return wind_ms
    
    return None

def get_wind_direction():
    """Obtiene dirección del viento"""
    if ads is None or len(adc_channels) < 4:
        return None, None
    
    try:
        voltage = adc_channels[3].voltage  # A0
        
        if voltage is None or voltage <= 0:
            return None, None
        
        resistance = 10000 * voltage / (VCC - voltage)
        
        closest_angle = None
        smallest_error = math.inf
        for angle, res_nom in DIRECTION_TABLE.items():
            error = abs(res_nom - resistance)
            if error < smallest_error:
                smallest_error = error
                closest_angle = angle
        
        tolerance = 0.15
        if closest_angle is not None and smallest_error <= DIRECTION_TABLE[closest_angle] * tolerance:
            return closest_angle, COMPASS.get(closest_angle, "")
        return None, None
        
    except Exception as e:
        return None, None

def read_irradiance():
    """Lee sensor de irradiancia"""
    if ads is None or len(adc_channels) < 3:
        return 0.0, 0.0
    
    try:
        IRRADIANCE_CALIBRATION_FACTOR = 1000.0 / 75.0
        
        # IRR- (Y4)
        if not set_mux_channel(4):
            return 0.0, 0.0
        voltage_minus = adc_channels[2].voltage
        
        # IRR+ (Y5)
        if not set_mux_channel(5):
            return 0.0, 0.0
        voltage_plus = adc_channels[2].voltage
        
        # Diferencial
        irradiance_voltage = abs(voltage_plus - voltage_minus)
        irradiance_voltage_mV = abs(irradiance_voltage * 1000.0)
        irradiance_wm2 = (irradiance_voltage_mV * IRRADIANCE_CALIBRATION_FACTOR)
        
        return irradiance_voltage, irradiance_wm2
        
    except Exception as e:
        return 0.0, 0.0

def read_dht22():
    """Lee temperatura y humedad del DHT22"""
    try:
        temp = dhtDevice.temperature
        humidity = dhtDevice.humidity
        return temp, humidity
    except RuntimeError as e:
        return None, None
    except Exception as e:
        return None, None

def read_all_weather_data():
    """Lee todos los datos meteorológicos"""
    data = {}
    
    # DHT22
    temp_dht, hum_dht = read_dht22()
    data['dht_temperature'] = temp_dht
    data['dht_humidity'] = hum_dht
    
    # Viento - mantener última velocidad válida
    wind_speed = get_wind_speed()
    data['wind_speed'] = wind_speed  # Puede ser None, se maneja después
    
    wind_angle, wind_dir = get_wind_direction()
    data['wind_angle'] = wind_angle
    data['wind_direction'] = wind_dir
    
    # Lluvia
    if system_start_time:
        elapsed_hours = (time.time() - system_start_time) / 3600
    else:
        elapsed_hours = 0
    rain_mm_total = rain_count_total * MM_PER_TICK
    data['rain_total'] = rain_mm_total
    data['elapsed_hours'] = elapsed_hours
    
    # Irradiancia
    irr_voltage, irr_wm2 = read_irradiance()
    data['irradiance_voltage'] = irr_voltage
    data['irradiance'] = irr_wm2
    
    return data

def setup_display():
    """Configura la pantalla inicial estática"""
    print(TerminalControl.CLEAR_SCREEN, end='')
    print(TerminalControl.HOME_CURSOR, end='')
    print(TerminalControl.HIDE_CURSOR, end='')
    
    # Título
    print(TerminalControl.goto(1, 1), end='')
    print("╔═══════════════════════════════════════════════════════════════╗")
    print(TerminalControl.goto(2, 1), end='')
    print("║                  ESTACIÓN METEOROLÓGICA                      ║")
    print(TerminalControl.goto(3, 1), end='')
    print("║              Monitoreo en Tiempo Real - VCC: 3.294V          ║")
    print(TerminalControl.goto(4, 1), end='')
    print("╚═══════════════════════════════════════════════════════════════╝")
    
    # Sección Temperatura y Humedad
    print(TerminalControl.goto(6, 1), end='')
    print("╔══ TEMPERATURA Y HUMEDAD AMBIENTE (DHT22) ════════════════════╗")
    print(TerminalControl.goto(7, 1), end='')
    print("║  Temperatura:         °C │ Humedad:            %           ║")
    print(TerminalControl.goto(8, 1), end='')
    print("╚═══════════════════════════════════════════════════════════════╝")
    
    # Sección Viento
    print(TerminalControl.goto(10, 1), end='')
    print("╔══ VIENTO ═════════════════════════════════════════════════════╗")
    print(TerminalControl.goto(11, 1), end='')
    print("║  Velocidad:       m/s │ Dirección:                         ║")
    print(TerminalControl.goto(12, 1), end='')
    print("║  (         km/h)      │ Ángulo:           °                ║")
    print(TerminalControl.goto(13, 1), end='')
    print("╚═══════════════════════════════════════════════════════════════╝")
    
    # Sección Precipitación
    print(TerminalControl.goto(15, 1), end='')
    print("╔══ PRECIPITACIÓN ══════════════════════════════════════════════╗")
    print(TerminalControl.goto(16, 1), end='')
    print("║  Acumulado:        mm │ Tiempo:         h                  ║")
    print(TerminalControl.goto(17, 1), end='')
    print("╚═══════════════════════════════════════════════════════════════╝")
    
    # Sección Irradiancia
    print(TerminalControl.goto(19, 1), end='')
    print("╔══ IRRADIANCIA SOLAR ══════════════════════════════════════════╗")
    print(TerminalControl.goto(20, 1), end='')
    print("║  Irradiancia:       W/m² │ Voltaje:         mV              ║")
    print(TerminalControl.goto(21, 1), end='')
    print("╚═══════════════════════════════════════════════════════════════╝")
    
    # Línea de estado
    print(TerminalControl.goto(23, 1), end='')
    print("─────────────────────────────────────────────────────────────")
    print(TerminalControl.goto(24, 1), end='')
    print("  Estado:")
    print(TerminalControl.goto(25, 1), end='')
    print("  Presiona Ctrl+C para detener")

def update_display(weather_data, measurement_count, error_count):
    """Actualiza los valores en la pantalla estática"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    
    # Actualizar timestamp y contador
    print(TerminalControl.goto(24, 11), end='')
    print(f"Medición #{measurement_count:05d} - {timestamp} - Errores: {error_count}     ")
    
    # DHT22 - Temperatura y Humedad
    print(TerminalControl.goto(7, 17), end='')
    if weather_data['dht_temperature'] is not None:
        print(f"{weather_data['dht_temperature']:6.2f}", end='')
    else:
        print(" ERROR", end='')
    
    print(TerminalControl.goto(7, 38), end='')
    if weather_data['dht_humidity'] is not None:
        print(f"{weather_data['dht_humidity']:6.1f}", end='')
    else:
        print(" ERROR", end='')
    
    # Viento - Velocidad y Dirección
    print(TerminalControl.goto(11, 17), end='')
    if weather_data['wind_speed'] is not None:
        wind_kph = weather_data['wind_speed'] * 3.6
        print(f"{weather_data['wind_speed']:6.2f}", end='')
        print(TerminalControl.goto(12, 5), end='')
        print(f"{wind_kph:6.1f}", end='')
    else:
        # Mantener valores anteriores si no hay nueva lectura
        print("      ", end='')  # No cambiar el display
        print(TerminalControl.goto(12, 5), end='')
        print("      ", end='')  # No cambiar el display
    
    print(TerminalControl.goto(11, 37), end='')
    if weather_data['wind_direction'] is not None:
        print(f"{weather_data['wind_direction']:>6}", end='')
    else:
        print(" ERROR", end='')
    
    print(TerminalControl.goto(12, 29), end='')
    if weather_data['wind_angle'] is not None:
        print(f"{weather_data['wind_angle']:6.1f}", end='')
    else:
        print(" ERROR", end='')
    
    # Precipitación
    print(TerminalControl.goto(16, 17), end='')
    print(f"{weather_data['rain_total']:6.2f}", end='')
    
    print(TerminalControl.goto(16, 37), end='')
    print(f"{weather_data['elapsed_hours']:6.1f}", end='')
    
    # Irradiancia
    print(TerminalControl.goto(20, 17), end='')
    print(f"{weather_data['irradiance']:7.1f}", end='')
    
    print(TerminalControl.goto(20, 40), end='')
    voltage_mv = weather_data['irradiance_voltage'] * 1000
    print(f"{voltage_mv:6.2f}", end='')
    
    # Forzar actualización del terminal
    sys.stdout.flush()

def print_station_info():
    """Muestra información de la estación meteorológica"""
    print("\n" + "="*65)
    print("           CONFIGURACIÓN ESTACIÓN METEOROLÓGICA")
    print("="*65)
    print(f"VCC del sistema:          {VCC:.3f} V")
    print(f"DHT22 (GPIO {DHT22_PIN}):           Temperatura y humedad ambiente")
    print(f"Anemómetro (GPIO {ANEMOMETER_PIN}):      {KPH_PER_COUNT_PER_SEC} km/h por pulso/segundo")
    print(f"Pluviómetro (GPIO {RAIN_SENSOR_PIN}):       {MM_PER_TICK:.4f} mm por pulso")
    print(f"Veleta (ADS1115 A0):      16 direcciones cardinales")
    print(f"Irradiancia (MUX Y4-Y5):  Factor de calibración: {1000.0/75.0:.2f}")
    
    print(f"\nEspecificaciones:")
    print(f"  Precisión viento:       ±0.1 m/s")
    print(f"  Precisión lluvia:       ±0.28 mm")
    print(f"  Resolución dirección:   22.5° (16 puntos)")
    print(f"  Rango temperatura:      -40°C a +80°C")
    print(f"  Precisión humedad:      ±2%")
    print("="*65)

# ======================== FUNCIÓN PRINCIPAL ========================
def main():
    global running
    
    # Configurar manejo de señales
    signal.signal(signal.SIGINT, signal_handler)
    
    # Mostrar información de configuración
    print_station_info()
    
    # Inicializar hardware
    if not initialize_hardware():
        print("Error: No se pudo inicializar el hardware meteorológico")
        return
    
    print("\nPresiona Enter para iniciar el monitor meteorológico...")
    input()
    
    # Configurar pantalla estática
    setup_display()
    
    measurement_count = 0
    error_count = 0
    last_measurement_time = time.time()
    last_dht_time = time.time()
    
    # Variables para mantener últimos valores válidos
    last_valid_dht_temp = None
    last_valid_dht_humidity = None
    last_valid_wind_speed = None
    last_valid_wind_angle = None
    last_valid_wind_direction = None
    last_wind_update = time.time()
    
    try:
        while running:
            current_time = time.time()
            
            # Actualizar cada segundo
            if current_time - last_measurement_time >= 1.0:
                measurement_count += 1
                
                # Leer datos meteorológicos
                weather_data = read_all_weather_data()
                
                # DHT22 cada 3 segundos
                if current_time - last_dht_time >= 3.0:
                    new_dht_temp, new_dht_humidity = read_dht22()
                    if new_dht_temp is not None and new_dht_humidity is not None:
                        last_valid_dht_temp = new_dht_temp
                        last_valid_dht_humidity = new_dht_humidity
                    last_dht_time = current_time
                
                # Manejar datos de viento (mantener últimos valores válidos)
                if weather_data['wind_speed'] is not None:
                    last_valid_wind_speed = weather_data['wind_speed']
                    last_wind_update = current_time
                    
                if weather_data['wind_angle'] is not None and weather_data['wind_direction'] is not None:
                    last_valid_wind_angle = weather_data['wind_angle']
                    last_valid_wind_direction = weather_data['wind_direction']
                
                # Usar últimos valores válidos para display
                weather_data['dht_temperature'] = last_valid_dht_temp
                weather_data['dht_humidity'] = last_valid_dht_humidity
                weather_data['wind_speed'] = last_valid_wind_speed
                weather_data['wind_angle'] = last_valid_wind_angle
                weather_data['wind_direction'] = last_valid_wind_direction
                
                # Contar errores SOLO cuando hay problemas reales
                current_errors = 0
                
                # DHT22: error si no hemos tenido lecturas válidas en 10 segundos
                if last_valid_dht_temp is None and current_time - last_dht_time > 10:
                    current_errors += 1
                    
                # Viento: error si no hemos tenido lecturas de velocidad en 5 segundos
                if last_valid_wind_speed is None and current_time - last_wind_update > 5:
                    current_errors += 1
                    
                # Dirección del viento: error si nunca hemos tenido lectura válida
                if last_valid_wind_direction is None and measurement_count > 10:
                    current_errors += 1
                
                if current_errors > 0:
                    error_count += 1
                
                # Actualizar pantalla
                update_display(weather_data, measurement_count, error_count)
                
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
        print("║           MONITOR TERMINADO                   ║")
        print("╚═══════════════════════════════════════════════╝")
        print(f"Total de mediciones realizadas: {measurement_count}")
        print(f"Ciclos con errores: {error_count}")
        
        if measurement_count > 0:
            success_rate = ((measurement_count - error_count) / measurement_count) * 100
            print(f"Tasa de éxito: {success_rate:.1f}%")
        
        # Mostrar estadísticas finales
        final_rain = rain_count_total * MM_PER_TICK
        if system_start_time:
            elapsed_time = (time.time() - system_start_time) / 3600
            print(f"Tiempo de monitoreo: {elapsed_time:.2f} horas")
            print(f"Precipitación total: {final_rain:.2f} mm")
        
        # Limpiar hardware
        try:
            # Cierra anemómetro (si existe)
            try:
                if anemometer:
                    anemometer.close()
            except Exception as e:
                print(f"Error cerrando anemómetro: {e}")

            # Cierra sensor de lluvia gpiozero si se usó
            try:
                if rain_sensor:
                    rain_sensor.close()
            except Exception as e:
                print(f"Error cerrando sensor de lluvia: {e}")

            # Esperar fin del hilo de lluvia si está vivo
            try:
                if 'rain_poll_thread' in globals() and rain_poll_thread and rain_poll_thread.is_alive():
                    print('Esperando cierre del hilo de lluvia...')
                    running = False
                    rain_poll_thread.join(timeout=1.0)
            except Exception as e:
                print(f"Error esperando hilo de lluvia: {e}")

            # Limpieza de GPIO y DHT
            try:
                GPIO.cleanup()
            except Exception as e:
                print(f"Error en GPIO.cleanup(): {e}")

            try:
                dhtDevice.exit()
            except Exception as e:
                print(f"Error cerrando DHT: {e}")

            print("Hardware limpiado correctamente")
        except Exception as e:
            print(f"Error limpiando hardware: {e}")
        
        print("Programa terminado")

if __name__ == "__main__":
    main()
