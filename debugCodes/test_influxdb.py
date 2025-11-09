#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script de prueba para conexión InfluxDB independiente del sistema principal
Uso: python test_influxdb.py
"""

import os
import sys
import time
from datetime import datetime

# Agregar path del directorio actual para importar influxdb_sender
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from influxdb_sender import (
        close_influxdb,
        init_influxdb,
        send_measurement_to_influx,
        test_influx_connection,
    )

    print("✓ Módulo influxdb_sender importado correctamente")
except ImportError as e:
    print(f"✗ Error importando influxdb_sender: {e}")
    sys.exit(1)


REQUIRED_ENV_VARS = [
    "SOLAR_DAQ_INFLUX_URL",
    "SOLAR_DAQ_INFLUX_TOKEN",
    "SOLAR_DAQ_INFLUX_ORG",
    "SOLAR_DAQ_INFLUX_BUCKET",
]


def validate_environment():
    """Verifica que las variables necesarias estén configuradas."""
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if not missing:
        return True

    print("✗ Variables de entorno faltantes para la prueba:")
    for var in missing:
        print(f"   - {var}")
    print()
    print("Configura las variables anteriores en tu sesión o dentro de ")
    print("/home/pi/.config/solar_daq.env antes de ejecutar este script.")
    return False


def test_complete_measurement():
    """Envía datos simulados completos del sistema"""
    print("\n=== TEST DATOS COMPLETOS ===")

    # Datos simulados realistas del sistema solar
    measurement_data = {
        # INA228 - Panel Solar 1
        "v0": 18.5,  # Voltaje panel 1
        "i0": 2.1,  # Corriente panel 1
        "p0": 38.85,  # Potencia panel 1
        "e0": 1.45,  # Energía panel 1 (Wh)
        # INA228 - Panel Solar 2
        "v1": 18.2,  # Voltaje panel 2
        "i1": 2.0,  # Corriente panel 2
        "p1": 36.4,  # Potencia panel 2
        "e1": 1.38,  # Energía panel 2 (Wh)
        # Irradiancia
        "irradiance": 875.5,  # W/m2
        # Termistores T0-T19 (temperaturas realistas)
        "T0": 28.5,
        "T1": 29.1,
        "T2": 27.8,
        "T3": 30.2,
        "T4": 28.9,
        "T5": 29.3,
        "T6": 27.5,
        "T7": 31.1,
        "T8": 28.7,
        "T9": 29.8,
        "T10": 30.5,
        "T11": 28.2,
        "T12": 29.6,
        "T13": 27.9,
        "T14": 30.8,
        "T15": 28.1,
        "T16": 29.4,
        "T17": 28.6,
        "T18": 30.1,
        "T19": 29.0,
        # Datos climáticos
        "rain_mm": 0.56,  # Lluvia acumulada en mm
        "wind_speed": 4.2,  # Velocidad viento m/s
        "wind_direction": 225.0,  # Dirección viento en grados
        "wind_dir_str": "SW",  # Dirección cardinal
        # DHT22 - Sensor ambiente
        "dht_temp": 26.8,  # Temperatura ambiente
        "dht_humidity": 68.5,  # Humedad relativa %
    }

    success = send_measurement_to_influx(measurement_data)

    if success:
        print("✓ Datos completos enviados exitosamente")
        return True
    else:
        print("✗ Error enviando datos completos")
        return False


def test_partial_measurement():
    """Envía datos parciales simulando sensores con fallas"""
    print("\n=== TEST DATOS PARCIALES ===")

    # Simular algunos sensores con falla (valores None o ausentes)
    partial_data = {
        "v0": 17.8,
        "i0": 1.9,
        "p0": 33.82,
        "e0": 1.23,
        # Panel 2 con falla - no enviar datos
        "irradiance": 650.0,
        # Solo algunos termistores
        "T0": 27.5,
        "T5": 28.1,
        "T10": 29.3,
        "T15": 27.8,
        # Sin datos de lluvia
        "wind_speed": 2.1,
        "dht_temp": 25.2,
        "dht_humidity": 72.1,
    }

    success = send_measurement_to_influx(partial_data)

    if success:
        print("✓ Datos parciales enviados exitosamente")
        return True
    else:
        print("✗ Error enviando datos parciales")
        return False


def main():
    print("=" * 60)
    print("        TEST INTEGRACIÓN INFLUXDB")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    if not validate_environment():
        return False

    # Paso 1: Inicializar conexión
    print("1. Inicializando conexión InfluxDB...")
    if not init_influxdb():
        print("✗ No se pudo conectar a InfluxDB")
        print("   Verifica las credenciales y la conectividad de red")
        return False

    # Paso 2: Test básico
    print("\n2. Test básico de conexión...")
    if not test_influx_connection():
        print("✗ Test básico falló")
        close_influxdb()
        return False

    # Paso 3: Test datos completos
    time.sleep(2)  # Esperar entre envíos
    if not test_complete_measurement():
        close_influxdb()
        return False

    # Paso 4: Test datos parciales
    time.sleep(2)
    if not test_partial_measurement():
        close_influxdb()
        return False

    # Paso 5: Cerrar conexión
    print("\n5. Cerrando conexión...")
    close_influxdb()

    print("\n" + "=" * 60)
    print("        ✓ TODOS LOS TESTS EXITOSOS")
    print("=" * 60)
    print()
    print("Próximos pasos:")
    print("1. Instalar influxdb-client en Raspberry Pi:")
    print("   pip install influxdb-client")
    print()
    print("2. El sistema ya está integrado automáticamente")
    print("   Los datos se envían cada minuto a InfluxDB")
    print()
    print("3. Solicita al administrador las credenciales de Grafana.")

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n✗ Test interrumpido por usuario")
        try:
            close_influxdb()
        except:
            pass
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error inesperado: {e}")
        try:
            close_influxdb()
        except:
            pass
        sys.exit(1)
