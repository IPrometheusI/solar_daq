#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import datetime
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import threading
import logging
import os
from pathlib import Path

# Configuración InfluxDB
ENV_VAR_MAP = {
    'url': 'SOLAR_DAQ_INFLUX_URL',
    'token': 'SOLAR_DAQ_INFLUX_TOKEN',
    'org': 'SOLAR_DAQ_INFLUX_ORG',
    'bucket': 'SOLAR_DAQ_INFLUX_BUCKET'
}

ENV_FILE_CANDIDATES = [
    os.environ.get('SOLAR_DAQ_ENV_FILE'),
    '/home/pi/.config/solar_daq.env'
]

INFLUX_CONFIG = {}


def _load_env_from_file():
    """Carga variables desde archivos estilo KEY=VALUE si existen."""
    for candidate in ENV_FILE_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if not path.exists() or not path.is_file():
            continue

        try:
            with path.open('r', encoding='utf-8') as env_file:
                for line in env_file:
                    stripped = line.strip()
                    if not stripped or stripped.startswith('#'):
                        continue

                    if '=' not in stripped:
                        continue

                    key, value = stripped.split('=', 1)
                    key = key.strip()
                    if not key or key in os.environ:
                        continue
                    os.environ[key] = value.strip()
        except OSError as exc:
            logging.warning(
                "No se pudo leer archivo de configuración %s: %s",
                path,
                exc,
            )


def _load_influx_config():
    """Obtiene configuración de InfluxDB desde variables de entorno."""
    config = {}
    missing = []

    for key, env_var in ENV_VAR_MAP.items():
        value = os.getenv(env_var)
        if value:
            config[key] = value
        else:
            missing.append(env_var)

    if missing:
        logging.error(
            "Faltan variables de entorno para InfluxDB: %s",
            ', '.join(missing),
        )
        print(
            "✗ Configuración InfluxDB incompleta. Define las variables: "
            + ', '.join(missing)
        )
        return None

    return config

# Lock para thread safety
influx_lock = threading.Lock()

# Cliente y write_api globales
influx_client = None
write_api = None

###################################
# init_influxdb
# Argumentos: Ninguno
# Return: bool - True si inicialización exitosa, False si falla
# Descripcion: Inicializa cliente InfluxDB y API de escritura
###################################
def init_influxdb():
    global influx_client, write_api, INFLUX_CONFIG

    _load_env_from_file()
    config = _load_influx_config()
    if config is None:
        return False

    INFLUX_CONFIG.clear()
    INFLUX_CONFIG.update(config)

    try:
        influx_client = InfluxDBClient(
            url=INFLUX_CONFIG['url'],
            token=INFLUX_CONFIG['token'],
            org=INFLUX_CONFIG['org']
        )

        write_api = influx_client.write_api(write_options=SYNCHRONOUS)

        # Test conexión
        health = influx_client.health()
        if health.status == "pass":
            print("✓ InfluxDB conectado correctamente")
            return True
        else:
            print(f"✗ InfluxDB health check falló: {health.status}")
            return False

    except Exception as e:
        print(f"✗ Error inicializando InfluxDB: {e}")
        return False

###################################
# close_influxdb
# Argumentos: Ninguno
# Return: None
# Descripcion: Cierra conexión InfluxDB de forma segura
###################################
def close_influxdb():
    global influx_client, write_api
    
    try:
        if write_api:
            write_api.close()
        if influx_client:
            influx_client.close()
        print("✓ InfluxDB desconectado")
    except Exception as e:
        print(f"Error cerrando InfluxDB: {e}")

###################################
# create_measurement_point
# Argumentos: measurement_data (dict) - Datos de medición del sistema
# Return: Point - Objeto Point para InfluxDB
# Descripcion: Crea punto de datos InfluxDB con todas las mediciones
###################################
def create_measurement_point(measurement_data):
    try:
        point = Point("solar_panel_measurement") \
            .time(datetime.utcnow(), WritePrecision.NS)
        
        # Datos INA228 - Panel Solar 1
        if 'v0' in measurement_data and measurement_data['v0'] is not None:
            point.field("panel1_voltage", float(measurement_data['v0']))
        if 'i0' in measurement_data and measurement_data['i0'] is not None:
            point.field("panel1_current", float(measurement_data['i0']))
        if 'p0' in measurement_data and measurement_data['p0'] is not None:
            point.field("panel1_power", float(measurement_data['p0']))
        if 'e0' in measurement_data and measurement_data['e0'] is not None:
            point.field("panel1_energy", float(measurement_data['e0']))
            
        # Datos INA228 - Panel Solar 2  
        if 'v1' in measurement_data and measurement_data['v1'] is not None:
            point.field("panel2_voltage", float(measurement_data['v1']))
        if 'i1' in measurement_data and measurement_data['i1'] is not None:
            point.field("panel2_current", float(measurement_data['i1']))
        if 'p1' in measurement_data and measurement_data['p1'] is not None:
            point.field("panel2_power", float(measurement_data['p1']))
        if 'e1' in measurement_data and measurement_data['e1'] is not None:
            point.field("panel2_energy", float(measurement_data['e1']))
            
        # Irradiancia
        if 'irradiance' in measurement_data and measurement_data['irradiance'] is not None:
            point.field("irradiance", float(measurement_data['irradiance']))
            
        # Termistores T0-T19
        for i in range(20):
            temp_key = f'T{i}'
            if temp_key in measurement_data and measurement_data[temp_key] is not None:
                try:
                    temp_val = float(measurement_data[temp_key])
                    if not (temp_val != temp_val):  # Check for NaN
                        point.field(f"thermistor_{i:02d}_temp", temp_val)
                except (ValueError, TypeError):
                    pass
                    
        # Datos climáticos
        if 'rain_mm' in measurement_data and measurement_data['rain_mm'] is not None:
            point.field("rain_accumulation", float(measurement_data['rain_mm']))
        if 'wind_speed' in measurement_data and measurement_data['wind_speed'] is not None:
            point.field("wind_speed", float(measurement_data['wind_speed']))
        if 'wind_direction' in measurement_data and measurement_data['wind_direction'] is not None:
            point.field("wind_direction", float(measurement_data['wind_direction']))
            
        # DHT22
        if 'dht_temp' in measurement_data and measurement_data['dht_temp'] is not None:
            point.field("ambient_temperature", float(measurement_data['dht_temp']))
        if 'dht_humidity' in measurement_data and measurement_data['dht_humidity'] is not None:
            point.field("ambient_humidity", float(measurement_data['dht_humidity']))
            
        # Tags adicionales
        point.tag("system", "raspberry_pi")
        point.tag("location", "solar_farm")
        
        return point
        
    except Exception as e:
        print(f"Error creando punto InfluxDB: {e}")
        return None

###################################
# send_measurement_to_influx
# Argumentos: measurement_data (dict) - Datos de medición
# Return: bool - True si envío exitoso, False si falla
# Descripcion: Envía datos de medición a InfluxDB con manejo de errores
###################################
def send_measurement_to_influx(measurement_data):
    global influx_client, write_api
    
    if not influx_client or not write_api:
        print("InfluxDB no inicializado")
        return False
    if not INFLUX_CONFIG:
        print("Configuración InfluxDB no disponible")
        return False
    
    with influx_lock:
        try:
            point = create_measurement_point(measurement_data)
            if point is None:
                return False
                
            write_api.write(INFLUX_CONFIG['bucket'], INFLUX_CONFIG['org'], point)
            print("✓ Datos enviados a InfluxDB")
            return True
            
        except Exception as e:
            print(f"✗ Error enviando datos a InfluxDB: {e}")
            return False

###################################
# test_influx_connection
# Argumentos: Ninguno  
# Return: bool - True si test exitoso, False si falla
# Descripcion: Prueba conexión enviando dato de prueba
###################################
def test_influx_connection():
    test_data = {
        'v0': 12.5,
        'i0': 1.2,
        'p0': 15.0,
        'irradiance': 850.0,
        'T0': 25.5,
        'dht_temp': 24.0,
        'dht_humidity': 65.0,
        'wind_speed': 3.5,
        'rain_mm': 0.0
    }
    
    print("Enviando datos de prueba a InfluxDB...")
    return send_measurement_to_influx(test_data)

if __name__ == "__main__":
    # Test independiente del módulo
    print("=== TEST INFLUXDB SENDER ===")
    
    if init_influxdb():
        if test_influx_connection():
            print("✓ Test completado exitosamente")
        else:
            print("✗ Test falló")
        close_influxdb()
    else:
        print("✗ No se pudo conectar a InfluxDB")
