#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Delete InfluxDB points in a local (America/Costa_Rica) time window by converting to UTC.

Usage:
    python delete_influx_range.py
    (Will prompt for date and time range interactively)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Dict

try:
    # Python 3.9+
    from zoneinfo import ZoneInfo
except Exception:
    # Fallback for older Python
    try:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    except Exception as e:
        print(
            "ERROR: zoneinfo not available. Use Python 3.9+ or install backports.zoneinfo",
            file=sys.stderr,
        )
        raise

try:
    from influxdb_client import InfluxDBClient
except Exception as e:
    print("ERROR: Missing dependency 'influxdb-client'. Install with:", file=sys.stderr)
    print("       pip install influxdb-client", file=sys.stderr)
    raise

# Configuración InfluxDB
# IMPORTANTE: Configurar variables de entorno o editar estos valores
INFLUX_CONFIG = {
    "url": os.getenv("INFLUX_URL", "http://your-influxdb-server.com"),
    "token": os.getenv("INFLUX_TOKEN", "your-influxdb-token-here"),
    "org": os.getenv("INFLUX_ORG", "your-org"),
    "bucket": os.getenv("INFLUX_BUCKET", "your-bucket"),
    "measurement": "solar_panel_measurement",
}

CR_TZ = ZoneInfo("America/Costa_Rica")


###################################
# local_to_utc_iso
# Argumentos:
#   - date_str (str): Fecha en formato 'YYYY-MM-DD'
#   - time_str (str): Hora en formato 'HH:MM' (24h, hora local CR)
# Return: str - Timestamp en formato ISO8601 UTC con 'Z', ej: '2025-10-02T21:55:00Z'
# Descripcion: Convierte fecha y hora local de Costa Rica a timestamp UTC en formato ISO8601
###################################
def local_to_utc_iso(date_str: str, time_str: str) -> str:
    """Convierte fecha/hora local CR a UTC ISO8601"""
    dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(
        tzinfo=CR_TZ
    )
    return dt_local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")


###################################
# build_predicate
# Argumentos:
#   - measurement (str): Nombre de la medición en InfluxDB
#   - tags (Dict[str, str]): Diccionario de tags para filtrar
# Return: str - String de predicado para operación de eliminación
# Descripcion: Construye predicado de eliminación usando _measurement y tags (Delete API NO soporta _field)
###################################
def build_predicate(measurement: str, tags: Dict[str, str]) -> str:
    """Construye predicado de eliminación para InfluxDB Delete API"""
    parts = [f'_measurement="{measurement}"']
    for k, v in tags.items():
        parts.append(f'{k}="{v}"')
    return " AND ".join(parts)


###################################
# flux_filter_expr
# Argumentos:
#   - measurement (str): Nombre de la medición en InfluxDB
#   - tags (Dict[str, str]): Diccionario de tags para filtrar
# Return: str - Expresión de filtro Flux para consultas de previsualización
# Descripcion: Construye expresión de filtro Flux para consultas de preview (soporta measurement y tags)
###################################
def flux_filter_expr(measurement: str, tags: Dict[str, str]) -> str:
    """Construye expresión de filtro Flux para queries de previsualización"""
    clauses = [f'r._measurement == "{measurement}"']
    for k, v in tags.items():
        clauses.append(f'r.{k} == "{v}"')
    inner = " and ".join(clauses)
    return f"fn: (r) => {inner}"


###################################
# preview_count
# Argumentos:
#   - client (InfluxDBClient): Cliente de InfluxDB conectado
#   - bucket (str): Nombre del bucket en InfluxDB
#   - org (str): Organización en InfluxDB
#   - start_utc (str): Timestamp UTC de inicio en formato ISO8601
#   - stop_utc (str): Timestamp UTC de fin en formato ISO8601
#   - measurement (str): Nombre de la medición
#   - tags (Dict[str, str]): Diccionario de tags para filtrar
# Return: int - Número total de puntos que coinciden con los criterios
# Descripcion: Cuenta cuántos puntos coinciden con el rango, medición y tags especificados
###################################
def preview_count(
    client: InfluxDBClient,
    bucket: str,
    org: str,
    start_utc: str,
    stop_utc: str,
    measurement: str,
    tags: Dict[str, str],
) -> int:
    """Cuenta puntos que coinciden con rango + measurement + tags en InfluxDB"""
    query_api = client.query_api()
    flt = flux_filter_expr(measurement, tags)
    flux = f"""
from(bucket: "{bucket}")
  |> range(start: {start_utc}, stop: {stop_utc})
  |> filter({flt})
  |> group()
  |> count(column: "_value")
  |> sum(column: "_value")
"""
    tables = query_api.query(flux, org=org)
    total = 0
    for table in tables:
        for record in table.records:
            if record.get_value() is not None:
                try:
                    total += int(record.get_value())
                except Exception:
                    pass
    return total


###################################
# main
# Argumentos: Ninguno
# Return: None
# Descripcion: Función principal interactiva que solicita fecha/hora y elimina datos de InfluxDB
#              tras confirmar con el usuario. Convierte tiempo local CR a UTC y muestra preview.
###################################
def main() -> None:
    print("=== Delete InfluxDB Data ===")
    print()
    print("Ingrese los datos para eliminar:")
    print()

    # Prompt for date
    while True:
        date_str = input("Fecha (YYYY-MM-DD, ejemplo: 2025-10-18): ").strip()
        try:
            # Validate date format
            datetime.strptime(date_str, "%Y-%m-%d")
            break
        except ValueError:
            print("Formato inválido. Use YYYY-MM-DD")

    # Prompt for start time
    while True:
        start_str = input("Hora inicio (HH:MM, ejemplo: 08:30): ").strip()
        try:
            # Validate time format
            datetime.strptime(start_str, "%H:%M")
            break
        except ValueError:
            print("Formato inválido. Use HH:MM")

    # Prompt for stop time
    while True:
        stop_str = input("Hora fin (HH:MM, ejemplo: 17:45): ").strip()
        try:
            # Validate time format
            datetime.strptime(stop_str, "%H:%M")
            break
        except ValueError:
            print("Formato inválido. Use HH:MM")

    start_utc = local_to_utc_iso(date_str, start_str)
    stop_utc = local_to_utc_iso(date_str, stop_str)

    tags: Dict[str, str] = {}
    predicate = build_predicate(INFLUX_CONFIG["measurement"], tags)

    print()
    print("=== Plan de Eliminación ===")
    print(f" URL        : {INFLUX_CONFIG['url']}")
    print(f" Org        : {INFLUX_CONFIG['org']}")
    print(f" Bucket     : {INFLUX_CONFIG['bucket']}")
    print(f" Measurement: {INFLUX_CONFIG['measurement']}")
    print(f" Tags       : {tags if tags else '(none)'}")
    print(f" Local CR   : {date_str} {start_str} -> {stop_str}")
    print(f" UTC Window : {start_utc} -> {stop_utc}  (stop is exclusive)")
    print(f" Predicate  : {predicate}")
    print("============================")
    print()

    with InfluxDBClient(
        url=INFLUX_CONFIG["url"], token=INFLUX_CONFIG["token"], org=INFLUX_CONFIG["org"]
    ) as client:
        # Preview count
        try:
            total = preview_count(
                client,
                INFLUX_CONFIG["bucket"],
                INFLUX_CONFIG["org"],
                start_utc,
                stop_utc,
                INFLUX_CONFIG["measurement"],
                tags,
            )
            print(f"Puntos encontrados que coinciden: {total}")
        except Exception as e:
            print(f"WARNING: Preview count failed: {e}", file=sys.stderr)
            total = -1

        print()
        confirm = input(
            "¿Confirmar eliminación de estos datos? Escriba 'DELETE' para confirmar: "
        ).strip()
        if confirm != "DELETE":
            print("Operación cancelada por el usuario.")
            return

        try:
            delete_api = client.delete_api()
            delete_api.delete(
                start=start_utc,
                stop=stop_utc,  # stop is exclusive
                predicate=predicate,
                bucket=INFLUX_CONFIG["bucket"],
                org=INFLUX_CONFIG["org"],
            )
            print("✅ Solicitud de eliminación completada exitosamente.")
        except Exception as e:
            print(f"ERROR: Delete failed: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
