#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import glob
import json
import math
import os
import signal
import sys
import threading
import time
from collections import deque
from contextlib import contextmanager
from datetime import datetime
from datetime import time as dt_time
from datetime import timedelta

import adafruit_ads1x15.ads1115 as ADS
import adafruit_dht
import board
import busio
import RPi.GPIO as GPIO
from adafruit_ads1x15.analog_in import AnalogIn
from adafruit_ina228 import INA228

hardware_lock = threading.Lock()

# InfluxDB integration
try:
    from influxdb_sender import (
        close_influxdb,
        init_influxdb,
        send_measurement_to_influx,
    )

    INFLUX_AVAILABLE = True
except ImportError:
    print("InfluxDB módulo no disponible - solo guardará en CSV")
    INFLUX_AVAILABLE = False

from gpiozero import Button, Device
from gpiozero.pins.pigpio import PiGPIOFactory

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

Device.pin_factory = PiGPIOFactory()

# Estado y configuración
STATE_FILE = "/home/pi/Desktop/sensor_system_state.json"
BACKUP_STATE_FILE = "/home/pi/Desktop/sensor_system_state_backup.json"

# INA228 Configuration
RSHUNT_OHMS = 0.002
IMAX_AMPS = 1.5
INA228_ADDRESSES = [0x40, 0x41]
AVG_TARGET = 1024
CT_TARGET_US = 1052
ADC_RANGE = 1

# Constantes del sistema
OPERATING_START_TIME = "05:00"  # Formato 24h "HH:MM"
OPERATING_END_TIME = "18:00"  # Formato 24h "HH:MM" (soporta cruce de medianoche)
MAX_RETRY_ATTEMPTS = 3
SENSOR_READ_TIMEOUT = 1
GPIO_SETUP_DELAY = 0.1  # Tiempo de estabilización del MUX (0.1s para irradiancia)
HARDWARE_RETRY_DELAY = 2
MAX_CONSECUTIVE_ERRORS = 10

# GPIO Configuration
try:
    GPIO.cleanup()
except:
    pass

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

MUX_S0 = 17
MUX_S1 = 27
MUX_S2 = 22

DHT22_PIN = 5
ANEMOMETER_PIN = 23
RAIN_SENSOR_PIN = 6

# Sensor setup
dhtDevice = adafruit_dht.DHT22(board.D5, use_pulseio=False)

# Wind and rain
KPH_PER_COUNT_PER_SEC = 2.4
MEASUREMENT_PERIOD = 1.0
wind_count = 0
last_wind_measurement = time.time()

MM_PER_TICK = 0.2794
rain_count = 0
rain_count_total = 0
terminal_rain_count = 0

# Termistores
A = 1.12924e-3
B = 2.34108e-4
C = 8.7755e-8
R_REF = 10000

THERMISTOR_REF_RESISTANCES = {
    "T0": 10030,
    "T1": 10050,
    "T2": 10000,
    "T3": 9990,
    "T4": 10000,
    "T5": 10020,
    "T6": 10030,
    "T7": 9990,
    "T8": 10000,
    "T9": 10020,
    "T10": 9980,
    "T11": 9980,
    "T12": 9970,
    "T13": 10030,
    "T14": 10000,
    "T15": 9980,
    "T16": 10010,
    "T17": 9980,
    "T18": 10010,
    "T19": 10000,
}

DIRECTION_TABLE = {
    0.0: 33_000,
    22.5: 6_570,
    45.0: 8_200,
    67.5: 891,
    90.0: 1_000,
    112.5: 688,
    135.0: 2_200,
    157.5: 1_410,
    180.0: 3_900,
    202.5: 3_140,
    225.0: 16_000,
    247.5: 14_120,
    270.0: 120_000,
    292.5: 42_120,
    315.0: 64_900,
    337.5: 21_880,
}

COMPASS = {
    0.0: "N",
    22.5: "NNE",
    45.0: "NE",
    67.5: "ENE",
    90.0: "E",
    112.5: "ESE",
    135.0: "SE",
    157.5: "SSE",
    180.0: "S",
    202.5: "SSW",
    225.0: "SW",
    247.5: "WSW",
    270.0: "W",
    292.5: "WNW",
    315.0: "NW",
    337.5: "NNW",
}

# Data storage
dht_temps = deque(maxlen=12)
dht_hums = deque(maxlen=12)
VCC = 3.294
wind_speeds_second = deque(maxlen=60)
thermistor_readings = {f"T{i}": deque(maxlen=12) for i in range(20)}

# Control variables
data_lock = threading.Lock()
running = False
measuring_active = True
file_recording_active = False
current_csv_file = None
ads = None
adc_channels = []
ina_sensors = {}
anemometer = None
rain_sensor = None
system_start_time = None
last_watchdog = time.time()
last_file_creation_day = -1
last_measurement_minute = -1

# InfluxDB control
influx_initialized = False

###################################
# OPERATING HOURS HELPER FUNCTIONS
###################################


###################################
# is_within_operating_hours
# Argumentos: now (datetime, opcional) - Momento a verificar, por defecto datetime.now()
# Return: bool - True si estamos dentro del horario de operación, False si no
# Descripcion: Verifica si estamos dentro del horario de operación. Soporta rangos que cruzan medianoche
###################################
def is_within_operating_hours(now=None):
    """Verifica si estamos dentro del horario de operación.
    Soporta rangos que cruzan medianoche (ej: 22:00 a 06:00)
    """
    if now is None:
        now = datetime.now()

    start_hour, start_min = map(int, OPERATING_START_TIME.split(":"))
    end_hour, end_min = map(int, OPERATING_END_TIME.split(":"))

    current_minutes = now.hour * 60 + now.minute
    start_minutes = start_hour * 60 + start_min
    end_minutes = end_hour * 60 + end_min

    # Si el rango cruza medianoche
    if end_minutes <= start_minutes:
        return current_minutes >= start_minutes or current_minutes < end_minutes
    else:
        return start_minutes <= current_minutes < end_minutes


###################################
# get_operating_start_hour
# Argumentos: Ninguno
# Return: int - Hora de inicio de operación (0-23)
# Descripcion: Extrae la hora de inicio del horario de operación
###################################
def get_operating_start_hour():
    """Retorna la hora de inicio de operación (0-23)"""
    return int(OPERATING_START_TIME.split(":")[0])


###################################
# get_operating_end_hour
# Argumentos: Ninguno
# Return: int - Hora de fin de operación (0-23)
# Descripcion: Extrae la hora de fin del horario de operación
###################################
def get_operating_end_hour():
    """Retorna la hora de fin de operación (0-23)"""
    return int(OPERATING_END_TIME.split(":")[0])


###################################
# is_time_to_create_daily_file
# Argumentos: now (datetime, opcional) - Momento a verificar
# Return: bool - True si es momento de crear archivo diario
# Descripcion: Verifica si estamos al inicio del horario de operación (hora y minuto 0)
###################################
def is_time_to_create_daily_file(now=None):
    """Verifica si es momento de crear el archivo diario (inicio del horario de operación)"""
    if now is None:
        now = datetime.now()

    start_hour, start_min = map(int, OPERATING_START_TIME.split(":"))
    return now.hour == start_hour and now.minute == start_min


###################################
# is_end_of_day
# Argumentos: now (datetime, opcional) - Momento a verificar
# Return: bool - True si estamos al final del día de operación
# Descripcion: Verifica si estamos al final del horario de operación (hora y minuto 0)
###################################
def is_end_of_day(now=None):
    """Verifica si estamos al final del día de operación"""
    if now is None:
        now = datetime.now()

    end_hour, end_min = map(int, OPERATING_END_TIME.split(":"))
    return now.hour == end_hour and now.minute == end_min


###################################
# TimeoutException
# Argumentos: Ninguno
# Return: Exception class
# Descripcion: Excepción personalizada para manejo de timeouts
###################################
class TimeoutException(Exception):
    pass


###################################
# timeout
# Argumentos: duration (int) - Duración del timeout en segundos
# Return: Context manager
# Descripcion: Context manager para implementar timeout en operaciones I2C
###################################
@contextmanager
def timeout(duration):
    def timeout_handler(signum, frame):
        raise TimeoutException(f"Timeout después de {duration} segundos")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(duration)

    try:
        yield
    finally:
        signal.alarm(0)


###################################
# _try_set
# Argumentos: prop_name (str), sensor (object), preferred (any), fallback (any, opcional)
# Return: None
# Descripcion: Intenta configurar una propiedad de sensor con valor preferido y fallback
###################################
def _try_set(prop_name, sensor, preferred, fallback=None):
    if not hasattr(sensor, prop_name):
        return
    try:
        setattr(sensor, prop_name, preferred)
    except Exception:
        if fallback is not None:
            try:
                setattr(sensor, prop_name, fallback)
            except Exception:
                pass


###################################
# setup_ina228
# Argumentos: i2c (busio.I2C), address (int) - Dirección I2C del sensor
# Return: INA228 object o excepción
# Descripcion: Configura un sensor INA228 con parámetros optimizados para máxima precisión
###################################
def setup_ina228(i2c, address):
    try:
        s = INA228(i2c, address=address)
        _try_set("adc_range", s, ADC_RANGE)
        s.set_calibration(shunt_res=RSHUNT_OHMS, max_current=IMAX_AMPS)
        _try_set("averaging_count", s, AVG_TARGET, fallback=7)
        _try_set("bus_voltage_conv_time", s, CT_TARGET_US, fallback=5)
        _try_set("shunt_voltage_conv_time", s, CT_TARGET_US, fallback=5)
        _try_set("temp_conv_time", s, CT_TARGET_US, fallback=5)
        _try_set("conversion_time_bus", s, CT_TARGET_US, fallback=5)
        _try_set("conversion_time_shunt", s, CT_TARGET_US, fallback=5)
        _try_set("conversion_time_temperature", s, CT_TARGET_US, fallback=5)

        if hasattr(s, "reset_accumulators"):
            s.reset_accumulators()

        return s

    except Exception as e:
        raise


# ======================== FUNCIÓN initialize_hardware MEJORADA ========================
###################################
# initialize_hardware
# Argumentos: Ninguno
# Return: bool - True si inicialización exitosa, False si falla
# Descripcion: Inicializa todo el hardware del sistema incluyendo I2C, GPIO, sensores y contadores
###################################
def initialize_hardware():
    """Inicializa todo el hardware con validación mejorada"""
    global ads, adc_channels, ina_sensors, anemometer, rain_sensor, system_start_time
    global rain_count, rain_count_total, wind_count  # ASEGURAR INICIALIZACIÓN

    # VALIDACIÓN CRÍTICA: Inicializar contadores explícitamente
    rain_count = 0
    rain_count_total = 0
    wind_count = 0

    # Cleanup previo
    try:
        if rain_sensor:
            rain_sensor.close()
        if anemometer:
            anemometer.close()
        GPIO.cleanup()
    except Exception:
        pass

    print("Inicializando hardware...")
    system_start_time = time.time()

    # Inicializar InfluxDB
    global influx_initialized
    if INFLUX_AVAILABLE:
        influx_initialized = init_influxdb()
        if influx_initialized:
            print("✓ InfluxDB inicializado")
        else:
            print("⚠ InfluxDB no pudo inicializarse - solo CSV")
    else:
        influx_initialized = False

    # GPIO Setup para MUX
    try:
        GPIO.setup([MUX_S0, MUX_S1, MUX_S2], GPIO.OUT)
        print("GPIO para MUX configurado correctamente")
    except Exception as e:
        print(f"Error configurando GPIO para MUX: {e}")
        return False

    # I2C Setup
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        print("Bus I2C inicializado")
    except Exception as e:
        print(f"Error inicializando I2C: {e}")
        return False

    # ADS1115 Setup con reintentos
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            ads = ADS.ADS1115(i2c, address=0x48)
            ads.gain = 1
            adc_channels = [
                AnalogIn(ads, ADS.P3),  # A3 -> Z1 (MUX1)
                AnalogIn(ads, ADS.P2),  # A2 -> Z2 (MUX2)
                AnalogIn(ads, ADS.P1),  # A1 -> Z3 (MUX3)
                AnalogIn(ads, ADS.P0),  # A0 -> Direccion del viento
            ]
            print("ADS1115 inicializado correctamente")
            break
        except Exception as e:
            print(
                f"Intento {attempt + 1}/{MAX_RETRY_ATTEMPTS} - Error inicializando ADS1115: {e}"
            )
            if attempt == MAX_RETRY_ATTEMPTS - 1:
                print("No se pudo inicializar ADS1115 después de varios intentos")
                return False
            time.sleep(HARDWARE_RETRY_DELAY)

    # INA228 Setup mejorado
    print("Inicializando sensores INA228...")
    ina_sensors = {}

    for address in INA228_ADDRESSES:
        try:
            sensor = setup_ina228(i2c, address)
            ina_sensors[address] = sensor
            print(f"✓ INA228 @ 0x{address:02X} listo")
        except Exception as e:
            print(f"⚠  No se pudo inicializar INA228 @ 0x{address:02X}: {e}")
            ina_sensors[address] = None

    # Verificar si tenemos al menos un sensor INA228
    active_ina_count = sum(1 for sensor in ina_sensors.values() if sensor is not None)
    if active_ina_count == 0:
        print("WARNING: Ningún INA228 disponible. Las mediciones de potencia serán 0.")
    else:
        print(f"✓ {active_ina_count}/{len(INA228_ADDRESSES)} sensores INA228 activos")

    # Configuración GPIOZERO con manejo de errores
    try:
        anemometer = Button(
            ANEMOMETER_PIN, pull_up=True, bounce_time=0.01  # pull-up interno
        )
        anemometer.when_pressed = wind_pulse
        anemometer.when_released = wind_pulse
        print("Anemómetro configurado correctamente con gpiozero")
    except Exception as e:
        print(f"Error configurando anemómetro: {e}")
        anemometer = None

    # Rain sensor setup mejorado
    try:
        GPIO.setup(RAIN_SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        rain_sensor = Button(RAIN_SENSOR_PIN, pull_up=True, bounce_time=0.01)
        rain_sensor.when_pressed = rain_pulse
        print("🌧️ Sensor lluvia configurado correctamente")
    except Exception as e:
        print(f"Error configurando sensor lluvia: {e}")
        rain_sensor = None

    # VALIDACIÓN FINAL: Verificar que los contadores siguen siendo números
    print(
        f"[INIT] Contadores inicializados: rain_count={rain_count}, wind_count={wind_count}"
    )

    return True


###################################
# wind_pulse
# Argumentos: Ninguno
# Return: None
# Descripcion: Callback para interrupciones del anemómetro, incrementa contador de pulsos de viento
###################################
def wind_pulse():
    global wind_count
    wind_count += 1


###################################
# rain_pulse
# Argumentos: Ninguno
# Return: None
# Descripcion: Callback para pulsos del pluviómetro, actualiza contadores de lluvia y muestra información
###################################
def rain_pulse():
    """Callback para pulsos del pluviómetro"""
    global rain_count, rain_count_total, terminal_rain_count
    rain_count += 1
    rain_count_total += 1
    terminal_rain_count += 1

    timestamp = datetime.now().strftime("%H:%M:%S")
    total_mm = rain_count_total * MM_PER_TICK
    min_rain = rain_count * MM_PER_TICK
    print(f"[{timestamp}] ⚡ LLUVIA #{rain_count_total} -> {total_mm:.3f}mm total")
    print(
        f"[{timestamp}] ⚡ LLUVIA #{terminal_rain_count} -> {min_rain:.3f}mm en un minuto"
    )


###################################
# set_mux_channel
# Argumentos: channel (int) - Canal del multiplexor (0-7)
# Return: bool - True si configuración exitosa, False si falla
# Descripcion: Configura el canal activo de los multiplexores CD74HC4051 mediante GPIO
###################################
def set_mux_channel(channel):
    try:
        GPIO.output(MUX_S0, channel & 0x01)
        GPIO.output(MUX_S1, (channel >> 1) & 0x01)
        GPIO.output(MUX_S2, (channel >> 2) & 0x01)
        time.sleep(GPIO_SETUP_DELAY)
        return True
    except Exception:
        return False


###################################
# calculate_resistance
# Argumentos: voltage (float), thermistor_id (str), vcc (float, opcional)
# Return: float - Resistencia calculada en ohms
# Descripcion: Calcula la resistencia de un termistor basado en el divisor de voltaje
###################################
def calculate_resistance(voltage, thermistor_id, vcc=VCC):
    if voltage <= 0 or voltage >= vcc:
        return float("inf")

    r_ref = THERMISTOR_REF_RESISTANCES.get(thermistor_id, 10000)
    return r_ref * voltage / (vcc - voltage)


###################################
# calculate_temperature
# Argumentos: resistance (float), thermistor_id (str)
# Return: float - Temperatura en grados Celsius
# Descripcion: Convierte resistencia de termistor a temperatura usando ecuación de Steinhart-Hart simplificada
###################################
def calculate_temperature(resistance, thermistor_id):
    if resistance <= 0:
        return float("nan")

    R0 = THERMISTOR_REF_RESISTANCES.get(thermistor_id, 10000.0)
    B = 3435.0
    T0 = 298.15

    T_kelvin = 1 / ((1 / T0) + (1 / B) * math.log(resistance / R0))
    return T_kelvin - 273.15


###################################
# get_wind_speed
# Argumentos: Ninguno
# Return: float o None - Velocidad del viento en m/s o None si no hay datos suficientes
# Descripcion: Calcula velocidad del viento basada en pulsos del anemómetro durante período de medición
###################################
def get_wind_speed():
    global wind_count, last_wind_measurement

    current_time = time.time()
    time_elapsed = current_time - last_wind_measurement

    if time_elapsed >= MEASUREMENT_PERIOD:
        cps = wind_count / time_elapsed
        wind_ms = cps * (KPH_PER_COUNT_PER_SEC / 3.6)
        wind_count = 0
        last_wind_measurement = current_time
        return wind_ms

    return None


###################################
# get_wind_direction_internal
# Argumentos: Ninguno
# Return: tuple (float, str) - Ángulo en grados y dirección cardinal, o (None, None) si falla
# Descripcion: Lee dirección del viento sin mutex interno, usa tabla de resistencias vs ángulos
###################################
def get_wind_direction_internal():
    if ads is None or len(adc_channels) < 4:
        return None, None

    try:
        voltage = adc_channels[3].voltage

        if voltage is None or voltage <= 0:
            return None, None

        resistance = R_REF * voltage / (3.3 - voltage)

        closest_angle = None
        smallest_error = math.inf
        for angle, res_nom in DIRECTION_TABLE.items():
            error = abs(res_nom - resistance)
            if error < smallest_error:
                smallest_error = error
                closest_angle = angle

        tolerance = 0.15
        if (
            closest_angle is not None
            and smallest_error <= DIRECTION_TABLE[closest_angle] * tolerance
        ):
            return closest_angle, COMPASS.get(closest_angle, "")
        return None, None

    except Exception:
        return None, None


###################################
# get_wind_direction
# Argumentos: Ninguno
# Return: tuple (float, str) - Ángulo en grados y dirección cardinal, o (None, None) si falla
# Descripcion: Lee dirección del viento con protección de mutex para acceso thread-safe
###################################
def get_wind_direction():
    if ads is None or len(adc_channels) < 4:
        return None, None

    with hardware_lock:
        return get_wind_direction_internal()


###################################
# read_thermistors_internal
# Argumentos: Ninguno
# Return: dict - Diccionario con temperaturas de todos los termistores {"T0": temp, ...}
# Descripcion: Lee todos los termistores (T0-T19) sin mutex interno, usa multiplexores
###################################
def read_thermistors_internal():
    temperatures = {}

    if ads is None or len(adc_channels) < 3:
        return temperatures

    try:
        # MUX1: T0-T7
        for ch in range(8):
            thermistor_id = f"T{ch}"
            if set_mux_channel(ch):
                try:
                    voltage = adc_channels[0].voltage
                    resistance = calculate_resistance(voltage, thermistor_id)
                    temp = calculate_temperature(resistance, thermistor_id)
                    temperatures[thermistor_id] = temp
                except Exception:
                    temperatures[thermistor_id] = float("nan")

        # MUX2: T8-T15
        for ch in range(8):
            thermistor_id = f"T{ch+8}"
            if set_mux_channel(ch):
                try:
                    voltage = adc_channels[1].voltage
                    resistance = calculate_resistance(voltage, thermistor_id)
                    temp = calculate_temperature(resistance, thermistor_id)
                    temperatures[thermistor_id] = temp
                except Exception:
                    temperatures[thermistor_id] = float("nan")

        # MUX3: T16-T19
        for ch in range(4):
            thermistor_id = f"T{ch+16}"
            if set_mux_channel(ch):
                try:
                    voltage = adc_channels[2].voltage
                    resistance = calculate_resistance(voltage, thermistor_id)
                    temp = calculate_temperature(resistance, thermistor_id)
                    temperatures[thermistor_id] = temp
                except Exception:
                    temperatures[thermistor_id] = float("nan")

    except Exception:
        pass

    return temperatures


###################################
# read_thermistors
# Argumentos: Ninguno
# Return: dict - Diccionario con temperaturas de todos los termistores
# Descripcion: Lee todos los termistores con protección de mutex para acceso thread-safe
###################################
def read_thermistors():
    if ads is None or len(adc_channels) < 3:
        return {}

    with hardware_lock:
        return read_thermistors_internal()


###################################
# read_irradiance
# Argumentos: Ninguno
# Return: tuple (float, float) - Voltaje diferencial y irradiancia en W/m2
# Descripcion: Lee sensor de irradiancia con protección de mutex para acceso thread-safe
###################################
def read_irradiance():
    if ads is None or len(adc_channels) < 3:
        return 0.0, 0.0

    with hardware_lock:
        return read_irradiance_internal()


###################################
# read_dht22
# Argumentos: Ninguno
# Return: tuple (float, float) - Temperatura en C y humedad en %, o (None, None) si falla
# Descripcion: Lee sensor de temperatura y humedad DHT22 con manejo de errores
###################################
def read_dht22():
    try:
        temp = dhtDevice.temperature
        humidity = dhtDevice.humidity
        return temp, humidity
    except RuntimeError:
        return None, None
    except Exception:
        return None, None


# ======================== FUNCIÓN read_ina228 CORREGIDA ========================
###################################
# read_ina228
# Argumentos: address (int) - Dirección I2C, name (str) - Nombre del sensor
# Return: dict o None - Diccionario con voltage, current, power, energy, temperature
# Descripcion: Lee datos de un sensor INA228 específico con validación completa y timeout
###################################
def read_ina228(address, name):
    """Lee datos de un INA228 específico con validación completa de None"""
    sensor = ina_sensors.get(address)
    if sensor is None:
        return None

    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            with timeout(SENSOR_READ_TIMEOUT):
                values = {}

                # VALIDACIÓN CRÍTICA: Asegurar que no hay None
                try:
                    voltage_raw = sensor.bus_voltage
                    values["voltage"] = voltage_raw if voltage_raw is not None else 0.0
                except Exception:
                    values["voltage"] = 0.0

                try:
                    current_raw = sensor.current
                    values["current"] = current_raw if current_raw is not None else 0.0
                except Exception:
                    values["current"] = 0.0

                try:
                    power_raw = sensor.power
                    values["power"] = power_raw if power_raw is not None else 0.0
                except Exception:
                    values["power"] = 0.0

                try:
                    energy_raw = getattr(sensor, "energy", 0.0)
                    values["energy"] = energy_raw if energy_raw is not None else 0.0
                except Exception:
                    values["energy"] = 0.0

                try:
                    temp_raw = getattr(sensor, "die_temperature", float("nan"))
                    values["temperature"] = (
                        temp_raw if temp_raw is not None else float("nan")
                    )
                except Exception:
                    values["temperature"] = float("nan")

                return values

        except (TimeoutException, Exception):
            if attempt < 1:
                time.sleep(1)

    # Si fallan todos los intentos, devolver valores por defecto
    return {
        "voltage": 0.0,
        "current": 0.0,
        "power": 0.0,
        "energy": 0.0,
        "temperature": float("nan"),
    }


# ======================== FUNCIÓN read_irradiance_internal CORREGIDA ========================
###################################
# read_irradiance_internal
# Argumentos: Ninguno
# Return: tuple (float, float) - Voltaje diferencial y irradiancia en W/m2
# Descripcion: Lee sensor de irradiancia sin mutex interno, medición diferencial en canales Y4/Y5
###################################
def read_irradiance_internal():
    """Lee irradiancia SIN mutex interno - con validación de None"""
    if ads is None or len(adc_channels) < 3:
        return 0.0, 0.0

    try:
        IRRADIANCE_CALIBRATION_FACTOR = 1000.0 / 75.0

        # IRR- (Y4 - canal 4 del MUX)
        if not set_mux_channel(4):
            return 0.0, 0.0
        time.sleep(0.1)  # Tiempo de estabilización del ADS después del cambio de canal
        voltage_minus = adc_channels[2].voltage
        # VALIDACIÓN: Asegurar que no es None
        if voltage_minus is None:
            voltage_minus = 0.0

        # IRR+ (Y5 - canal 5 del MUX)
        if not set_mux_channel(5):
            return 0.0, 0.0
        time.sleep(0.1)  # Tiempo de estabilización del ADS después del cambio de canal
        voltage_plus = adc_channels[2].voltage
        # VALIDACIÓN: Asegurar que no es None
        if voltage_plus is None:
            voltage_plus = 0.0

        # Diferencial con validación
        irradiance_voltage = abs(voltage_plus - voltage_minus)
        irradiance_voltage_mV = abs(irradiance_voltage * 1000.0)
        irradiance_wm2 = irradiance_voltage_mV * IRRADIANCE_CALIBRATION_FACTOR

        # Asegurar que los valores de retorno no son None - retornar voltaje en mV
        return (
            irradiance_voltage_mV if irradiance_voltage_mV is not None else 0.0,
            irradiance_wm2 if irradiance_wm2 is not None else 0.0,
        )

    except Exception as e:
        print(f"Error leyendo irradiancia: {e}")
        return 0.0, 0.0


###################################
# validate_ina228_data
# Argumentos: ina_data (dict o None) - Datos del sensor INA228
# Return: dict - Diccionario con valores validados (voltage, current, power, energy)
# Descripcion: Valida y sanitiza datos de INA228 asegurando que no haya valores None
###################################
def validate_ina228_data(ina_data):
    """Valida datos de INA228 y retorna valores seguros"""
    if not ina_data or not isinstance(ina_data, dict):
        return {"voltage": 0.0, "current": 0.0, "power": 0.0, "energy": 0.0}

    voltage = ina_data.get("voltage", 0.0)
    voltage = voltage if voltage is not None else 0.0

    current = ina_data.get("current", 0.0)
    current = current if current is not None else 0.0

    power = ina_data.get("power", 0.0)
    power = power if power is not None else 0.0

    energy_raw = ina_data.get("energy", 0.0)
    energy_raw = energy_raw if energy_raw is not None else 0.0
    energy = energy_raw / 3600.0  # Convertir a Wh

    return {"voltage": voltage, "current": current, "power": power, "energy": energy}


###################################
# calculate_average
# Argumentos: data_list (list) - Lista de valores numéricos
# Return: float o None - Promedio de valores válidos o None si no hay datos
# Descripcion: Calcula promedio excluyendo valores None y NaN
###################################
def calculate_average(data_list):
    valid_data = [x for x in data_list if x is not None and not math.isnan(x)]
    if valid_data:
        return sum(valid_data) / len(valid_data)
    return None


###################################
# save_system_state
# Argumentos: Ninguno
# Return: bool - True si guardado exitoso, False si falla
# Descripcion: Guarda estado actual del sistema en archivos JSON principal y backup
###################################
def save_system_state():
    global current_csv_file, measuring_active, last_file_creation_day, rain_count_total, system_start_time, file_recording_active

    try:
        now = datetime.now()
        state = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "current_csv_file": current_csv_file,
            "measuring_active": measuring_active,
            "file_recording_active": file_recording_active,
            "last_file_creation_day": last_file_creation_day,
            "current_day": now.timetuple().tm_yday,
            "current_year": now.year,
            "rain_count_total": rain_count_total,
            "system_start_time": system_start_time,
            "file_creation_time": None,
        }

        if current_csv_file and os.path.exists(current_csv_file):
            state["file_creation_time"] = os.path.getctime(current_csv_file)
            state["file_size"] = os.path.getsize(current_csv_file)

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        with open(BACKUP_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        return True

    except Exception:
        return False


###################################
# load_system_state
# Argumentos: Ninguno
# Return: dict o None - Estado del sistema cargado o None si no existe
# Descripcion: Carga estado del sistema desde archivos JSON, intenta backup si principal falla
###################################
def load_system_state():
    state_files = [STATE_FILE, BACKUP_STATE_FILE]

    for state_file in state_files:
        try:
            if not os.path.exists(state_file):
                continue

            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)

            return state

        except Exception:
            continue

    return None


###################################
# should_continue_with_existing_file
# Argumentos: state (dict) - Estado del sistema previamente guardado
# Return: tuple (bool, str) - Si debe continuar y razón
# Descripcion: Determina si el sistema debe continuar con archivo CSV existente o crear nuevo
###################################
def should_continue_with_existing_file(state):
    if not state:
        return False, "No hay estado previo"

    now = datetime.now()
    current_day = now.timetuple().tm_yday
    current_year = now.year

    if (
        state.get("current_day") != current_day
        or state.get("current_year") != current_year
    ):
        return False, "Cambió el día/año"

    if not is_within_operating_hours(now):
        return False, "Fuera de horario de medición"

    old_csv_file = state.get("current_csv_file")
    if not old_csv_file or not os.path.exists(old_csv_file):
        return False, "Archivo CSV anterior no existe"

    try:
        with open(old_csv_file, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
            if not first_line or "DateTime" not in first_line:
                return False, "Archivo CSV corrupto"
    except Exception:
        return False, "Error verificando archivo"

    if not state.get("file_recording_active", False):
        return False, "Sistema no estaba grabando"

    return True, old_csv_file


###################################
# restore_system_state
# Argumentos: state (dict) - Estado del sistema a restaurar
# Return: bool - True si restauración exitosa, False si falla
# Descripcion: Restaura variables globales del sistema desde estado guardado
###################################
def restore_system_state(state):
    global current_csv_file, measuring_active, last_file_creation_day, rain_count_total, system_start_time, file_recording_active

    try:
        current_csv_file = state.get("current_csv_file")
        measuring_active = state.get("measuring_active", True)
        file_recording_active = state.get("file_recording_active", False)
        last_file_creation_day = state.get("last_file_creation_day", -1)
        rain_count_total = state.get("rain_count_total", 0)

        saved_start_time = state.get("system_start_time")
        if saved_start_time:
            system_start_time = saved_start_time
        else:
            system_start_time = time.time()

        return True

    except Exception:
        return False


###################################
# cleanup_state_file
# Argumentos: Ninguno
# Return: None
# Descripcion: Elimina archivos de estado JSON al finalizar el sistema
###################################
def cleanup_state_file():
    try:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        if os.path.exists(BACKUP_STATE_FILE):
            os.remove(BACKUP_STATE_FILE)
    except Exception:
        pass


###################################
# find_current_day_file
# Argumentos: Ninguno
# Return: str o None - Ruta del archivo CSV del día actual o None si no existe
# Descripcion: Busca archivo CSV existente para el día actual en directorio de mediciones
###################################
def find_current_day_file():
    try:
        mediciones_dir = "/home/pi/Desktop/Mediciones"
        if not os.path.exists(mediciones_dir):
            return None

        now = datetime.now()
        current_date_str = now.strftime("%Y%m%d")
        pattern = f"data_{current_date_str}_*.csv"
        files = glob.glob(os.path.join(mediciones_dir, pattern))

        if files:
            latest_file = max(files, key=os.path.getmtime)
            return latest_file

        return None

    except Exception:
        return None


###################################
# check_and_create_missing_file
# Argumentos: Ninguno
# Return: bool - True si archivo encontrado/creado, False si no es posible
# Descripcion: Verifica existencia de archivo CSV diario y lo crea si es necesario
###################################
def check_and_create_missing_file():
    global current_csv_file, file_recording_active, last_file_creation_day

    now = datetime.now()
    current_day = now.timetuple().tm_yday

    if not is_within_operating_hours(now):
        return False

    existing_file = find_current_day_file()
    if existing_file:
        current_csv_file = existing_file
        file_recording_active = True
        last_file_creation_day = current_day
        return True

    if current_csv_file and os.path.exists(current_csv_file) and file_recording_active:
        return False

    if last_file_creation_day == current_day:
        return False

    try:
        if create_csv_file():
            return True
        else:
            return False
    except Exception:
        return False


###################################
# initialize_system_with_enhanced_recovery
# Argumentos: Ninguno
# Return: bool - True si inicialización exitosa, False si falla
# Descripcion: Inicializa sistema con recuperación avanzada de estado previo
###################################
def initialize_system_with_enhanced_recovery():
    global current_csv_file, measuring_active, last_file_creation_day, file_recording_active

    saved_state = load_system_state()

    if saved_state:
        should_continue, reason = should_continue_with_existing_file(saved_state)

        if should_continue:
            if restore_system_state(saved_state):
                now = datetime.now()
                if is_within_operating_hours(now):
                    file_recording_active = True
                else:
                    file_recording_active = False
                return True

    current_csv_file = None
    measuring_active = True
    file_recording_active = False
    last_file_creation_day = -1

    if check_and_create_missing_file():
        return True
    else:
        return False


###################################
# enhanced_main_loop_check
# Argumentos: Ninguno
# Return: str - Estado del chequeo ("file_created" o "normal")
# Descripcion: Verifica integridad del sistema y crea archivos faltantes durante bucle principal
###################################
def enhanced_main_loop_check():
    global last_file_creation_day, current_csv_file, file_recording_active

    now = datetime.now()
    current_minute = now.minute

    if (
        current_minute % 5 == 0
        and is_within_operating_hours(now)
        and (
            not current_csv_file
            or not os.path.exists(current_csv_file)
            or not file_recording_active
        )
    ):

        if check_and_create_missing_file():
            return "file_created"

    return "normal"


###################################
# print_detailed_measurement
# Argumentos: Ninguno
# Return: None
# Descripcion: Imprime medición detallada y estructurada de todos los sensores en terminal
###################################
def print_detailed_measurement():
    """Imprime medición detallada en formato estructurado"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    global terminal_rain_count

    print("=" * 120)
    print(" " * 40 + "SISTEMA DE ADQUISICION DE DATOS SOLAR")
    print("=" * 120)
    print(f"[{timestamp}] === MEDICION PRINCIPAL ===")

    # === SENSORES INA228 ===
    print("\n--- SENSORES INA228 ---")
    for addr in INA228_ADDRESSES:
        name = f"INA0x{addr:02X}"
        ina_data = read_ina228(addr, name)
        if ina_data:
            v = ina_data["voltage"]
            i = ina_data["current"]
            p = ina_data["power"]
            e = ina_data["energy"] / 3600.0  # Convertir a Wh
            print(f"{name} -> V={v:.2f} V | I={i:.2f} A | P={p:.2f} W | E={e:.2f} Wh")
        else:
            print(f"{name} -> ERROR EN LECTURA")

    # === IRRADIANCIA ===
    print("\n--- IRRADIANCIA ---")
    # Lectura instantánea de irradiancia
    try:
        irr_voltage, irr_wm2 = read_irradiance()
        print(f"Irradiancia: {irr_wm2:.2f} W/m2")
    except Exception as e:
        print(f"Irradiancia: ERROR - {e}")

    # === TERMISTORES (en dos columnas) ===
    print("\n--- TERMISTORES ---")
    with data_lock:
        # Obtener promedios de termistores
        avg_thermistors = {}
        for sensor in thermistor_readings.keys():
            avg_temp = calculate_average(list(thermistor_readings[sensor]))
            if avg_temp is not None and is_valid_temperature(avg_temp):
                avg_thermistors[sensor] = avg_temp

    # Imprimir en dos columnas (T0-T9 con T10-T19)
    for i in range(10):
        left_sensor = f"T{i}"
        right_sensor = f"T{i+10}"

        left_temp = avg_thermistors.get(left_sensor)
        right_temp = avg_thermistors.get(right_sensor)

        left_str = f"{left_temp:.1f}C" if left_temp is not None else "ERR"
        right_str = f"{right_temp:.1f}C" if right_temp is not None else "ERR"

        print(f"{left_sensor} | {left_str:<6} || {right_sensor} | {right_str:<6}")

    # === CLIMA ===
    print("\n--- CLIMA ---")

    # Dirección del viento
    wind_angle, wind_dir = get_wind_direction()
    if wind_angle is not None:
        print(f"Direccion viento: {wind_angle:.1f}° ({wind_dir})")
    else:
        print("Direccion viento: SIN LECTURA")

    # Velocidad del viento promedio
    with data_lock:
        avg_wind = calculate_average(list(wind_speeds_second))

    if avg_wind is not None:
        print(f"Velocidad viento promedio: {avg_wind:.2f} m/s")
    else:
        print("Velocidad viento promedio: SIN DATOS")

    # Lluvia
    rain_mm_minute = terminal_rain_count * MM_PER_TICK
    rain_mm_total = rain_count_total * MM_PER_TICK
    print(f"Lluvia acumulada (min): {rain_mm_minute:.2f} mm")
    print(f"Lluvia total (dia): {rain_mm_total:.2f} mm")
    terminal_rain_count = 0

    # === DHT22 ===
    print("\n--- DHT22 ---")
    with data_lock:
        avg_temp_dht = calculate_average(list(dht_temps))
        avg_hum_dht = calculate_average(list(dht_hums))

    if avg_temp_dht is not None:
        print(f"Temperatura DHT: {avg_temp_dht:.1f}C")
        print(f"Humedad DHT: {avg_hum_dht:.1f}%")
    else:
        print("Temperatura DHT: SIN DATOS")
        print("Humedad DHT: SIN DATOS")

    # === ESTADO DEL SISTEMA ===
    print("\n--- ESTADO DEL SISTEMA ---")
    csv_status = "SI" if file_recording_active else "NO"
    print(f"Grabando CSV: {csv_status}")

    print("=" * 120)


###################################
# create_csv_file
# Argumentos: Ninguno
# Return: bool - True si creación exitosa, False si falla
# Descripcion: Crea nuevo archivo CSV diario con encabezados completos
###################################
def create_csv_file():
    global current_csv_file, rain_count_total, file_recording_active

    now = datetime.now()
    filename = f"data_{now.strftime('%Y%m%d_%H%M%S')}.csv"
    mediciones_dir = "/home/pi/Desktop/Mediciones"
    os.makedirs(mediciones_dir, exist_ok=True)
    current_csv_file = f"{mediciones_dir}/{filename}"

    try:
        with open(current_csv_file, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)

            header = [
                "V0[V]",
                "V1[V]",
                "I0[A]",
                "I1[A]",
                "P0[W]",
                "P1[W]",
                "E0[Wh]",
                "E1[Wh]",
                "Irr[W/m2]",
            ]

            for i in range(20):
                header.append(f"T{i}[°C]")

            header.extend(
                [
                    "Rain[mm]",
                    "Wind_Speed[m/s]",
                    "Wind_Direction",
                    "DHT_HUM[%]",
                    "DHT_TEMP[°C]",
                    "DateTime",
                ]
            )

            writer.writerow(header)

        # Reset daily counters
        rain_count_total = 0

        # Reset energy accumulators in INA228 sensors for daily start
        print("Reseteando acumuladores de energía para nuevo día...")
        for address, sensor in ina_sensors.items():
            if sensor is not None:
                try:
                    if hasattr(sensor, "reset_accumulators"):
                        sensor.reset_accumulators()
                        print(f"✓ Energía reseteada en INA228 @ 0x{address:02X}")
                except Exception as e:
                    print(
                        f"⚠ Error reseteando energía en INA228 @ 0x{address:02X}: {e}"
                    )

        file_recording_active = True
        print(f"Archivo creado: {filename}")
        save_system_state()
        return True

    except Exception as e:
        print(f"Error creando CSV: {e}")
        return False


# ======================== FUNCIÓN record_measurement CORREGIDA ========================
###################################
# record_measurement
# Argumentos: Ninguno
# Return: bool - True si medición exitosa, False si falla
# Descripcion: Función principal que lee todos los sensores y registra datos en CSV
###################################
def record_measurement():
    """Registra una medición con validación completa de None"""
    global current_csv_file, file_recording_active, rain_count, terminal_rain_count

    now = datetime.now()

    # Verificar horario
    if not is_within_operating_hours(now):
        print(f"[{now.strftime('%H:%M:%S')}] ⏰ Fuera de horario de grabación")
        try:
            print_detailed_measurement()
        except Exception as e:
            print(f"Error imprimiendo medición: {e}")
        return True

    if not file_recording_active or not current_csv_file:
        print(f"[{now.strftime('%H:%M:%S')}] ⏸️  Grabación no activa")
        try:
            print_detailed_measurement()
        except Exception as e:
            print(f"Error imprimiendo medición: {e}")
        return True

    try:
        print(f"[{now.strftime('%H:%M:%S')}] === MEDICIÓN PRINCIPAL ===")

        # PASO 1: INA228 (I2C diferente, no conflicta con ADS1115)
        print("[MAIN] Leyendo INA228...")
        ina_data = {}
        for addr in INA228_ADDRESSES:
            name = f"INA{addr-0x3F}"
            ina_data[addr] = read_ina228(addr, name)

        # PASO 2: Hardware ADS1115 - UN SOLO MUTEX para toda la operación
        print("[MAIN] Accediendo hardware ADS1115...")
        with hardware_lock:  # MUTEX ÚNICO
            print("[MAIN] Lock adquirido para hardware completo")

            # Leer TODOS los sensores ADS1115 de una vez
            temps = read_thermistors_internal()  # SIN mutex interno
            irradiance_v, irradiance = read_irradiance_internal()  # SIN mutex interno
            wind_angle, wind_dir = get_wind_direction_internal()  # SIN mutex interno

        print("[MAIN] Hardware ADS1115 completado y liberado")

        # PASO 3: Procesar datos sin hardware - CON VALIDACIÓN COMPLETA DE None
        # INA228 datos (sensor 1 = 0x40, sensor 2 = 0x41)
        ina1_validated = validate_ina228_data(ina_data.get(0x40))
        ina2_validated = validate_ina228_data(ina_data.get(0x41))

        # Extraer valores validados
        v0 = ina1_validated["voltage"]
        i0 = ina1_validated["current"]
        p0 = ina1_validated["power"]
        e0 = ina1_validated["energy"]

        v1 = ina2_validated["voltage"]
        i1 = ina2_validated["current"]
        p1 = ina2_validated["power"]
        e1 = ina2_validated["energy"]

        # VALIDACIÓN CRÍTICA IRRADIANCIA
        if irradiance is None:
            irradiance = 0.0

        # VALIDACIÓN CRÍTICA RAIN_COUNT
        if rain_count is None:
            rain_count = 0
            print("[WARNING] rain_count era None, corregido a 0")

        # Promedios de datos thread
        with data_lock:
            avg_temp_dht = calculate_average(list(dht_temps))
            avg_hum_dht = calculate_average(list(dht_hums))
            avg_wind = calculate_average(list(wind_speeds_second))

            # Termistores promediados
            avg_thermistors = {}
            for sensor in thermistor_readings.keys():
                avg_thermistors[sensor] = calculate_average(
                    list(thermistor_readings[sensor])
                )

        # Escribir archivo
        if file_recording_active and current_csv_file:
            print("[MAIN] Escribiendo a CSV...")

            if not os.path.exists(current_csv_file):
                print("Archivo CSV no existe, creando...")
                if not create_csv_file():
                    return False

            with open(current_csv_file, "a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)

                # Crear fila de datos - TODOS LOS VALORES VALIDADOS
                row = [
                    f"{v0:.4f}",
                    f"{v1:.4f}",
                    f"{i0:.4f}",
                    f"{i1:.4f}",
                    f"{p0:.4f}",
                    f"{p1:.4f}",
                    f"{e0:.4f}",
                    f"{e1:.4f}",
                    f"{irradiance:.2f}",
                ]

                # Añadir termistores T0-T19
                for i in range(20):
                    sensor_key = f"T{i}"
                    temp_val = avg_thermistors.get(sensor_key, float("nan"))
                    if temp_val is None or math.isnan(temp_val):
                        row.append("N/A")
                    else:
                        row.append(f"{temp_val:.2f}")

                # Dirección del viento
                wind_dir_str = (
                    f"{wind_angle:.1f}°({wind_dir})"
                    if wind_angle is not None
                    else "N/A"
                )

                # Lluvia acumulada - VALIDADO
                rain_mm_minute = rain_count * MM_PER_TICK

                # Añadir resto de datos
                row.extend(
                    [
                        f"{rain_mm_minute:.2f}",
                        f"{avg_wind:.2f}" if avg_wind is not None else "N/A",
                        wind_dir_str,
                        f"{avg_hum_dht:.1f}" if avg_hum_dht is not None else "N/A",
                        f"{avg_temp_dht:.2f}" if avg_temp_dht is not None else "N/A",
                        now.strftime("%Y-%m-%d %H:%M:%S"),
                    ]
                )

                # Reset rain_count DESPUÉS de usar
                rain_count = 0

                writer.writerow(row)

                # Enviar datos a InfluxDB
                if influx_initialized:
                    try:
                        influx_data = {
                            "v0": v0,
                            "v1": v1,
                            "i0": i0,
                            "i1": i1,
                            "p0": p0,
                            "p1": p1,
                            "e0": e0,
                            "e1": e1,
                            "irradiance": irradiance,
                            "rain_mm": rain_mm_minute,
                            "wind_speed": avg_wind,
                            "wind_direction": wind_angle,
                            "wind_dir_str": wind_dir,
                            "dht_temp": avg_temp_dht,
                            "dht_humidity": avg_hum_dht,
                        }

                        # Añadir termistores
                        for i in range(20):
                            sensor_key = f"T{i}"
                            temp_val = avg_thermistors.get(sensor_key)
                            if temp_val is not None and not math.isnan(temp_val):
                                influx_data[sensor_key] = temp_val

                        send_measurement_to_influx(influx_data)
                    except Exception as e:
                        print(f"Error enviando a InfluxDB: {e}")

        print(f"[{now.strftime('%H:%M:%S')}] ✓ Medición principal completada")

        # Mostrar medición
        try:
            print_detailed_measurement()
        except Exception as e:
            print(f"Error imprimiendo medición: {e}")

        save_system_state()
        return True

    except Exception as e:
        print(f"[MAIN] ERROR en record_measurement: {e}")
        # DEBUG EXTRA: Mostrar variables problemáticas
        try:
            print(f"[DEBUG] Estado de variables críticas:")
            print(f"  rain_count: {rain_count} (tipo: {type(rain_count)})")
            print(f"  irradiance: {irradiance} (tipo: {type(irradiance)})")
            print(f"  ina1_data: {ina1_data}")
            print(f"  ina2_data: {ina2_data}")
        except:
            print("[DEBUG] Error mostrando estado de variables")

        return False


###################################
# process_end_of_day
# Argumentos: Ninguno
# Return: None
# Descripcion: Procesa finalización del día cerrando archivos y limpiando estado
###################################
def process_end_of_day():
    global current_csv_file, file_recording_active

    if not current_csv_file or not os.path.exists(current_csv_file):
        return

    file_recording_active = False
    print("FIN DEL DÍA - Archivo completado")

    save_system_state()

    try:
        file_size = os.path.getsize(current_csv_file) / 1024
        print(f"Archivo: {os.path.basename(current_csv_file)} ({file_size:.2f} KB)")
    except Exception:
        pass

    current_csv_file = None
    cleanup_state_file()


###################################
# is_valid_temperature
# Argumentos: temp (float) - Temperatura a validar
# Return: bool - True si temperatura es válida, False si no
# Descripcion: Valida que temperatura esté en rango razonable (10-70C) y no sea None/NaN
###################################
def is_valid_temperature(temp):
    if temp is None or math.isnan(temp):
        return False
    return 10.0 <= temp <= 70.0


###################################
# measurement_thread
# Argumentos: Ninguno
# Return: None
# Descripcion: Hilo secundario para lectura continua de sensores ambientales
###################################
def measurement_thread():
    global wind_speeds_second, last_watchdog

    dht_counter = 0
    last_thermistor_read = 0

    while running:
        try:
            current_time = time.time()
            last_watchdog = current_time

            if measuring_active:
                # Wind speed
                wind_speed = get_wind_speed()
                if wind_speed is not None:
                    with data_lock:
                        wind_speeds_second.append(wind_speed)

                # Thermistors every 5 seconds
                if current_time - last_thermistor_read >= 5.0:
                    temps = read_thermistors()
                    with data_lock:
                        for sensor, temp in temps.items():
                            if is_valid_temperature(temp):
                                thermistor_readings[sensor].append(temp)
                    last_thermistor_read = current_time

                # Irradiance reading removed - now only instantaneous during main measurement

                # DHT22 every 5 seconds
                if dht_counter % 5 == 0:
                    temp_dht, hum_dht = read_dht22()
                    if temp_dht is not None:
                        with data_lock:
                            dht_temps.append(temp_dht)
                            dht_hums.append(hum_dht)

            dht_counter += 1
            time.sleep(1)

        except Exception:
            time.sleep(2)


###################################
# main
# Argumentos: Ninguno
# Return: None
# Descripcion: Función principal del sistema, controla bucle principal y manejo de errores
###################################
def main():
    global running, measuring_active, last_file_creation_day, last_measurement_minute

    print("=" * 120)
    print(" " * 40 + "SISTEMA DE ADQUISICION DE DATOS SOLAR")
    print("=" * 120)
    print(f"Horario: {OPERATING_START_TIME} - {OPERATING_END_TIME}")
    print("Ctrl+C para detener")
    print("=" * 120)

    if not initialize_hardware():
        print("Error inicializando hardware")
        return

    recovered = initialize_system_with_enhanced_recovery()
    if recovered:
        print("Estado recuperado - Continuando")

    running = True
    measure_thread = threading.Thread(target=measurement_thread)
    measure_thread.daemon = True
    measure_thread.start()

    loop_counter = 0
    consecutive_errors = 0
    last_minute_processed = -1
    last_hour_processed = -1

    try:
        print("Sistema iniciado")

        now = datetime.now()
        if is_within_operating_hours(now):
            print(f"HORARIO ACTIVO ({now.strftime('%H:%M')})")
        else:
            print(f"Esperando horario activo ({now.strftime('%H:%M')})")

        time.sleep(5)

        while True:
            try:
                loop_counter += 1
                now = datetime.now()
                current_day = now.timetuple().tm_yday
                current_hour = now.hour
                current_minute = now.minute

                # Check for missing files every 5 minutes
                if loop_counter % 300 == 0:
                    loop_status = enhanced_main_loop_check()
                    if loop_status == "file_created":
                        consecutive_errors = 0

                # Create daily file at start hour
                if (
                    is_time_to_create_daily_file(now)
                    and current_day != last_file_creation_day
                ):

                    print(f"[{now.strftime('%H:%M:%S')}] Creando archivo diario")
                    try:
                        if create_csv_file():
                            last_file_creation_day = current_day
                            last_measurement_minute = -1
                            consecutive_errors = 0
                        else:
                            consecutive_errors += 1
                    except Exception:
                        consecutive_errors += 1

                # End of day at end hour
                elif is_end_of_day(now):
                    print(f"[{now.strftime('%H:%M:%S')}] Finalizando día")
                    try:
                        process_end_of_day()
                        consecutive_errors = 0
                    except Exception:
                        consecutive_errors += 1

                # Take measurements every minute
                elif (
                    current_minute != last_measurement_minute
                    and current_minute != last_minute_processed
                ):

                    if now.second < 5:
                        try:
                            last_minute_processed = current_minute
                            measurement_start = time.time()
                            success = record_measurement()
                            measurement_time = time.time() - measurement_start

                            if success:
                                last_measurement_minute = current_minute
                                consecutive_errors = 0
                            else:
                                consecutive_errors += 1

                        except Exception:
                            consecutive_errors += 1

                # Reinitialize on too many errors
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print("Demasiados errores - reinicializando")
                    try:
                        if initialize_hardware():
                            consecutive_errors = 0
                    except Exception:
                        pass
                    time.sleep(30)

                # Adaptive sleep
                if is_within_operating_hours(now):
                    time.sleep(1)
                else:
                    time.sleep(5)

                if current_hour != last_hour_processed:
                    last_minute_processed = -1
                    last_hour_processed = current_hour

            except Exception:
                consecutive_errors += 1
                time.sleep(10)

                if consecutive_errors > 5:
                    last_minute_processed = -1
                    last_measurement_minute = -1

    except KeyboardInterrupt:
        print("\nSistema detenido")

        if system_start_time:
            elapsed_time = (time.time() - system_start_time) / 3600
            final_rain = rain_count_total * MM_PER_TICK
            print(
                f"Tiempo operacion: {elapsed_time:.2f}h | Lluvia total: {final_rain:.2f}mm"
            )

    except Exception as e:
        print(f"Error crítico: {e}")

    finally:
        running = False

        if file_recording_active and current_csv_file:
            try:
                process_end_of_day()
            except Exception:
                pass

        if measure_thread and measure_thread.is_alive():
            measure_thread.join(timeout=5)

        try:
            if rain_sensor:
                rain_sensor.close()
        except Exception:
            pass

        try:
            if anemometer:
                anemometer.close()
        except Exception:
            pass

        try:
            GPIO.cleanup()
        except Exception:
            pass

        try:
            dhtDevice.exit()
        except Exception:
            pass

        # Cerrar InfluxDB
        if influx_initialized and INFLUX_AVAILABLE:
            try:
                close_influxdb()
            except Exception:
                pass

        print("=" * 120)
        print(" " * 50 + "SISTEMA FINALIZADO")
        print("=" * 120)


if __name__ == "__main__":
    main()
