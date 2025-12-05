#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import threading
import time
from datetime import datetime

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# Configuración InfluxDB
# IMPORTANTE: Configurar variables de entorno o editar estos valores
INFLUX_CONFIG = {
    "url": os.getenv("INFLUX_URL", "http://your-influxdb-server.com"),
    "token": os.getenv("INFLUX_TOKEN", "your-influxdb-token-here"),
    "org": os.getenv("INFLUX_ORG", "your-org"),
    "bucket": os.getenv("INFLUX_BUCKET", "your-bucket"),
    "timeout": 10000,  # 10 segundos timeout en milisegundos
}

# Lock para thread safety
influx_lock = threading.Lock()

# Cliente y write_api globales
influx_client = None
write_api = None

# Variables de control para monitoreo de salud
last_successful_write = None
consecutive_failures = 0
connection_init_time = None
MAX_CONSECUTIVE_FAILURES = 5
CONNECTION_REFRESH_HOURS = 12  # Renovar conexión cada 12 horas


###################################
# init_influxdb
# Argumentos: force_reconnect (bool) - Forzar cierre de conexión existente antes de reconectar
# Return: bool - True si inicialización exitosa, False si falla
# Descripcion: Inicializa cliente InfluxDB y API de escritura con timeout y manejo robusto
###################################
def init_influxdb(force_reconnect=False):
    global influx_client, write_api, consecutive_failures, connection_init_time, last_successful_write

    # Si force_reconnect, cerrar conexión existente primero
    if force_reconnect and (influx_client is not None or write_api is not None):
        print("🔄 Forzando cierre de conexión InfluxDB existente...")
        try:
            close_influxdb()
        except Exception as e:
            print(f"Advertencia cerrando conexión previa: {e}")
        time.sleep(2)  # Esperar a que se liberen recursos

    try:
        # Crear cliente con timeout configurado
        influx_client = InfluxDBClient(
            url=INFLUX_CONFIG["url"],
            token=INFLUX_CONFIG["token"],
            org=INFLUX_CONFIG["org"],
            timeout=INFLUX_CONFIG["timeout"],
        )

        write_api = influx_client.write_api(write_options=SYNCHRONOUS)

        # Test conexión con timeout
        health = influx_client.health()
        if health.status == "pass":
            connection_init_time = time.time()
            consecutive_failures = 0
            last_successful_write = time.time()
            print(
                f"✓ InfluxDB conectado correctamente (timeout: {INFLUX_CONFIG['timeout']}ms)"
            )
            return True
        else:
            print(f"✗ InfluxDB health check falló: {health.status}")
            close_influxdb()
            return False

    except Exception as e:
        print(f"✗ Error inicializando InfluxDB: {e}")
        influx_client = None
        write_api = None
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
            write_api = None
        if influx_client:
            influx_client.close()
            influx_client = None
        print("✓ InfluxDB desconectado")
    except Exception as e:
        print(f"Error cerrando InfluxDB: {e}")


###################################
# check_connection_health
# Argumentos: Ninguno
# Return: bool - True si conexión está saludable, False si no
# Descripcion: Verifica el estado de salud de la conexión InfluxDB
###################################
def check_connection_health():
    if not influx_client:
        return False

    try:
        health = influx_client.health()
        return health.status == "pass"
    except Exception as e:
        print(f"⚠ Health check falló: {e}")
        return False


###################################
# needs_connection_refresh
# Argumentos: Ninguno
# Return: bool - True si la conexión necesita renovarse
# Descripcion: Determina si la conexión debe renovarse por antigüedad
###################################
def needs_connection_refresh():
    if connection_init_time is None:
        return True

    hours_since_init = (time.time() - connection_init_time) / 3600
    return hours_since_init >= CONNECTION_REFRESH_HOURS


###################################
# auto_recover_connection
# Argumentos: Ninguno
# Return: bool - True si recuperación exitosa, False si falla
# Descripcion: Intenta recuperar automáticamente la conexión InfluxDB
###################################
def auto_recover_connection():
    print("🔧 Intentando recuperar conexión InfluxDB...")

    # Intentar reconexión con 3 intentos
    for attempt in range(3):
        try:
            if init_influxdb(force_reconnect=True):
                print(f"✓ Conexión recuperada en intento {attempt + 1}")
                return True
            else:
                print(f"✗ Intento {attempt + 1} falló")
                time.sleep(5)  # Esperar entre intentos
        except Exception as e:
            print(f"✗ Error en intento {attempt + 1}: {e}")
            time.sleep(5)

    print("✗ No se pudo recuperar la conexión después de 3 intentos")
    return False


###################################
# create_measurement_point
# Argumentos: measurement_data (dict) - Datos de medición del sistema
# Return: Point - Objeto Point para InfluxDB
# Descripcion: Crea punto de datos InfluxDB con todas las mediciones
###################################
def create_measurement_point(measurement_data):
    try:
        point = Point("solar_panel_measurement").time(
            datetime.utcnow(), WritePrecision.NS
        )

        # Datos INA228 - Panel Solar 1
        if "v0" in measurement_data and measurement_data["v0"] is not None:
            point.field("panel1_voltage", float(measurement_data["v0"]))
        if "i0" in measurement_data and measurement_data["i0"] is not None:
            point.field("panel1_current", float(measurement_data["i0"]))
        if "p0" in measurement_data and measurement_data["p0"] is not None:
            point.field("panel1_power", float(measurement_data["p0"]))
        if "e0" in measurement_data and measurement_data["e0"] is not None:
            point.field("panel1_energy", float(measurement_data["e0"]))

        # Datos INA228 - Panel Solar 2
        if "v1" in measurement_data and measurement_data["v1"] is not None:
            point.field("panel2_voltage", float(measurement_data["v1"]))
        if "i1" in measurement_data and measurement_data["i1"] is not None:
            point.field("panel2_current", float(measurement_data["i1"]))
        if "p1" in measurement_data and measurement_data["p1"] is not None:
            point.field("panel2_power", float(measurement_data["p1"]))
        if "e1" in measurement_data and measurement_data["e1"] is not None:
            point.field("panel2_energy", float(measurement_data["e1"]))

        # Irradiancia
        if (
            "irradiance" in measurement_data
            and measurement_data["irradiance"] is not None
        ):
            point.field("irradiance", float(measurement_data["irradiance"]))

        # Termistores T0-T19
        for i in range(20):
            temp_key = f"T{i}"
            if temp_key in measurement_data and measurement_data[temp_key] is not None:
                try:
                    temp_val = float(measurement_data[temp_key])
                    if not (temp_val != temp_val):  # Check for NaN
                        point.field(f"thermistor_{i:02d}_temp", temp_val)
                except (ValueError, TypeError):
                    pass

        # Datos climáticos
        if "rain_mm" in measurement_data and measurement_data["rain_mm"] is not None:
            point.field("rain_accumulation", float(measurement_data["rain_mm"]))
        if (
            "wind_speed" in measurement_data
            and measurement_data["wind_speed"] is not None
        ):
            point.field("wind_speed", float(measurement_data["wind_speed"]))
        if (
            "wind_direction" in measurement_data
            and measurement_data["wind_direction"] is not None
        ):
            point.field("wind_direction", float(measurement_data["wind_direction"]))

        # DHT22
        if "dht_temp" in measurement_data and measurement_data["dht_temp"] is not None:
            point.field("ambient_temperature", float(measurement_data["dht_temp"]))
        if (
            "dht_humidity" in measurement_data
            and measurement_data["dht_humidity"] is not None
        ):
            point.field("ambient_humidity", float(measurement_data["dht_humidity"]))

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
# Descripcion: Envía datos de medición a InfluxDB con recuperación automática
###################################
def send_measurement_to_influx(measurement_data):
    global consecutive_failures, last_successful_write

    # Verificar si necesitamos refrescar la conexión por antigüedad
    if needs_connection_refresh():
        print("⏰ Conexión InfluxDB antigua - refrescando preventivamente...")
        auto_recover_connection()

    if not influx_client or not write_api:
        print("InfluxDB no inicializado - intentando reconectar...")
        if not auto_recover_connection():
            return False

    with influx_lock:
        try:
            point = create_measurement_point(measurement_data)
            if point is None:
                consecutive_failures += 1
                return False

            write_api.write(INFLUX_CONFIG["bucket"], INFLUX_CONFIG["org"], point)

            # Actualizar estado de éxito
            last_successful_write = time.time()
            consecutive_failures = 0
            print("✓ Datos enviados a InfluxDB")
            return True

        except Exception as e:
            consecutive_failures += 1
            print(
                f"✗ Error enviando datos a InfluxDB (fallo #{consecutive_failures}): {e}"
            )

            # Si tenemos muchos fallos consecutivos, intentar recuperar conexión
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(
                    f"⚠ {consecutive_failures} fallos consecutivos - iniciando recuperación automática..."
                )
                if auto_recover_connection():
                    # Reintentar el envío una vez después de recuperar
                    try:
                        point = create_measurement_point(measurement_data)
                        if point:
                            write_api.write(
                                INFLUX_CONFIG["bucket"], INFLUX_CONFIG["org"], point
                            )
                            last_successful_write = time.time()
                            consecutive_failures = 0
                            print(
                                "✓ Datos enviados exitosamente después de recuperación"
                            )
                            return True
                    except Exception as retry_error:
                        print(f"✗ Reintento falló: {retry_error}")

            return False


###################################
# get_connection_stats
# Argumentos: Ninguno
# Return: dict - Estadísticas de la conexión
# Descripcion: Retorna información sobre el estado de la conexión
###################################
def get_connection_stats():
    stats = {
        "is_connected": influx_client is not None and write_api is not None,
        "consecutive_failures": consecutive_failures,
        "last_successful_write": last_successful_write,
        "connection_init_time": connection_init_time,
        "connection_age_hours": None,
    }

    if connection_init_time:
        stats["connection_age_hours"] = (time.time() - connection_init_time) / 3600

    return stats


###################################
# periodic_health_check
# Argumentos: Ninguno
# Return: bool - True si conexión está saludable o fue recuperada exitosamente
# Descripcion: Chequeo periódico de salud que se debe llamar regularmente
###################################
def periodic_health_check():
    global consecutive_failures

    # Verificar si la conexión está inicializada
    if not influx_client or not write_api:
        print("⚠ Chequeo periódico: InfluxDB no inicializado")
        return auto_recover_connection()

    # Verificar salud de la conexión
    if not check_connection_health():
        print("⚠ Chequeo periódico: Conexión no saludable")
        consecutive_failures += 1
        return auto_recover_connection()

    # Verificar si necesita refresco por antigüedad
    if needs_connection_refresh():
        print("⏰ Chequeo periódico: Conexión antigua, refrescando...")
        return auto_recover_connection()

    # Todo bien
    stats = get_connection_stats()
    print(
        f"✓ Chequeo periódico InfluxDB: OK (edad: {stats['connection_age_hours']:.1f}h, fallos: {consecutive_failures})"
    )
    return True


###################################
# test_influx_connection
# Argumentos: Ninguno
# Return: bool - True si test exitoso, False si falla
# Descripcion: Prueba conexión enviando dato de prueba
###################################
def test_influx_connection():
    test_data = {
        "v0": 12.5,
        "i0": 1.2,
        "p0": 15.0,
        "irradiance": 850.0,
        "T0": 25.5,
        "dht_temp": 24.0,
        "dht_humidity": 65.0,
        "wind_speed": 3.5,
        "rain_mm": 0.0,
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
