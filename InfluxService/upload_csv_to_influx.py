#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upload CSV data to InfluxDB with time range filtering.

CSV files format: data_YYYYMMDD_HHMMSS.csv
Located in: archivos_csv/

Usage:
    python upload_csv_to_influx.py
    (Will prompt for CSV file selection and time range interactively)
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, time
from pathlib import Path
from typing import Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
except Exception:
    try:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    except Exception as e:
        print(
            "ERROR: zoneinfo not available. Use Python 3.9+ or install backports.zoneinfo",
            file=sys.stderr,
        )
        raise

try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS
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
}

# Timezone Costa Rica
CR_TZ = ZoneInfo("America/Costa_Rica")
CSV_FOLDER = "archivos_csv"


###################################
# get_available_csv_files
# Argumentos: Ninguno
# Return: List[Path] - Lista ordenada de archivos CSV encontrados
# Descripcion: Obtiene todos los archivos CSV en la carpeta 'archivos_csv' que siguen
#              el patrón data_*.csv
###################################
def get_available_csv_files() -> List[Path]:
    """Obtiene lista ordenada de archivos CSV en carpeta archivos_csv"""
    csv_folder = Path(CSV_FOLDER)
    if not csv_folder.exists():
        print(f"ERROR: Folder '{CSV_FOLDER}' does not exist.", file=sys.stderr)
        return []

    csv_files = sorted(csv_folder.glob("data_*.csv"))
    return csv_files


###################################
# parse_filename_datetime
# Argumentos:
#   - filename (str): Nombre del archivo CSV
# Return: Optional[datetime] - Datetime en timezone CR o None si formato inválido
# Descripcion: Extrae fecha y hora del nombre de archivo con formato data_YYYYMMDD_HHMMSS.csv
###################################
def parse_filename_datetime(filename: str) -> Optional[datetime]:
    """Extrae datetime del nombre de archivo data_YYYYMMDD_HHMMSS.csv"""
    try:
        # Remove extension and prefix
        base = filename.replace(".csv", "").replace("data_", "")
        # Parse YYYYMMDD_HHMMSS
        dt = datetime.strptime(base, "%Y%m%d_%H%M%S")
        # Assign Costa Rica timezone
        return dt.replace(tzinfo=CR_TZ)
    except Exception:
        return None


###################################
# create_point_from_csv_row
# Argumentos:
#   - row (Dict[str, str]): Fila de datos del CSV como diccionario
#   - timestamp (datetime): Timestamp en timezone CR de la columna DateTime del CSV
# Return: Optional[Point] - Punto de InfluxDB o None si error
# Descripcion: Crea un Point de InfluxDB desde una fila CSV, mapeando columnas a fields
#              y agregando tags del sistema. Incluye datos de paneles, termistores y ambiente.
###################################
def create_point_from_csv_row(
    row: Dict[str, str], timestamp: datetime
) -> Optional[Point]:
    """Crea Point de InfluxDB desde fila CSV con todos los campos mapeados"""
    try:
        point = Point("solar_panel_measurement").time(
            timestamp.astimezone(ZoneInfo("UTC")), WritePrecision.NS
        )

        # Mapeo de columnas CSV a fields InfluxDB
        field_mappings = {
            "V0[V]": "panel1_voltage",
            "V1[V]": "panel2_voltage",
            "I0[A]": "panel1_current",
            "I1[A]": "panel2_current",
            "P0[W]": "panel1_power",
            "P1[W]": "panel2_power",
            "E0[Wh]": "panel1_energy",
            "E1[Wh]": "panel2_energy",
            "Irr[W/m2]": "irradiance",
            "Rain[mm]": "rain_accumulation",
            "Wind_Speed[m/s]": "wind_speed",
            "Wind_Direction": "wind_direction",
            "DHT_HUM[%]": "ambient_humidity",
            "DHT_TEMP[°C]": "ambient_temperature",
        }

        # Agregar fields principales
        for csv_col, influx_field in field_mappings.items():
            if csv_col in row and row[csv_col].strip():
                try:
                    # Special handling for Wind_Direction: extract degrees only
                    if csv_col == "Wind_Direction":
                        wind_val = row[csv_col].strip()
                        # Extract number before ° symbol or parenthesis
                        # Format examples: "90.0°(E)", "180.0°(S)", "270.0°(W)"
                        if "°" in wind_val:
                            wind_val = wind_val.split("°")[0]
                        elif "(" in wind_val:
                            wind_val = wind_val.split("(")[0]
                        value = float(wind_val)
                    else:
                        value = float(row[csv_col].strip())

                    point.field(influx_field, value)
                except (ValueError, TypeError):
                    pass

        # Agregar termistores T0-T19
        for i in range(20):
            temp_col = f"T{i}[°C]"
            if temp_col in row and row[temp_col].strip():
                try:
                    temp_val = float(row[temp_col].strip())
                    if not (temp_val != temp_val):  # Check for NaN
                        point.field(f"thermistor_{i:02d}_temp", temp_val)
                except (ValueError, TypeError):
                    pass

        # Tags adicionales
        point.tag("system", "raspberry_pi")
        point.tag("location", "solar_farm")

        return point

    except Exception as e:
        print(f"Error creating point: {e}")
        return None


###################################
# upload_csv_with_time_filter
# Argumentos:
#   - client (InfluxDBClient): Cliente de InfluxDB conectado
#   - csv_path (Path): Ruta al archivo CSV
#   - start_time (time): Hora de inicio del filtro
#   - end_time (time): Hora de fin del filtro
#   - file_date (datetime): Fecha del archivo CSV
# Return: int - Número de puntos subidos exitosamente
# Descripcion: Sube archivo CSV a InfluxDB filtrando filas por rango de tiempo.
#              Maneja rangos que cruzan medianoche. Procesa BOM UTF-8 si existe.
###################################
def upload_csv_with_time_filter(
    client: InfluxDBClient,
    csv_path: Path,
    start_time: time,
    end_time: time,
    file_date: datetime,
) -> int:
    """Sube CSV a InfluxDB filtrando por rango de tiempo, retorna puntos subidos"""
    write_api = client.write_api(write_options=SYNCHRONOUS)
    points_uploaded = 0
    points_skipped = 0

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            # Remove BOM if present
            content = f.read()
            if content.startswith("\ufeff"):
                content = content[1:]

            reader = csv.DictReader(content.splitlines(), skipinitialspace=True)

            for row in reader:
                # Parse timestamp from DateTime column
                if "DateTime" not in row or not row["DateTime"].strip():
                    continue

                try:
                    # DateTime format in CSV (assuming format like: YYYY-MM-DD HH:MM:SS)
                    dt_str = row["DateTime"].strip()
                    timestamp = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(
                        tzinfo=CR_TZ
                    )

                    # Filter by time range
                    row_time = timestamp.time()

                    # Handle time range that crosses midnight
                    if start_time <= end_time:
                        # Normal range (e.g., 08:00 to 17:00)
                        if not (start_time <= row_time <= end_time):
                            points_skipped += 1
                            continue
                    else:
                        # Range crosses midnight (e.g., 23:00 to 02:00)
                        if not (row_time >= start_time or row_time <= end_time):
                            points_skipped += 1
                            continue

                    point = create_point_from_csv_row(row, timestamp)
                    if point:
                        write_api.write(
                            INFLUX_CONFIG["bucket"], INFLUX_CONFIG["org"], point
                        )
                        points_uploaded += 1

                except Exception as e:
                    print(f"Warning: Error processing row: {e}")
                    continue

        print(f"✓ Uploaded {points_uploaded} points from {csv_path.name}")
        print(f"  Skipped {points_skipped} points outside time range")

    except Exception as e:
        print(f"✗ Error uploading {csv_path.name}: {e}", file=sys.stderr)

    finally:
        write_api.close()

    return points_uploaded


###################################
# main
# Argumentos: Ninguno
# Return: None
# Descripcion: Función principal interactiva que permite seleccionar archivo CSV de archivos_csv/,
#              especificar rango de tiempo, y subir datos filtrados a InfluxDB tras confirmación.
###################################
def main() -> None:
    print("=== CSV to InfluxDB Uploader ===")
    print()

    # Step 1: List available CSV files
    csv_files = get_available_csv_files()

    if not csv_files:
        print("No se encontraron archivos CSV en la carpeta 'archivos_csv/'")
        sys.exit(1)

    print("Archivos CSV disponibles:")
    for idx, csv_file in enumerate(csv_files, 1):
        file_dt = parse_filename_datetime(csv_file.name)
        if file_dt:
            print(f"  {idx}. {csv_file.name} - {file_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print(f"  {idx}. {csv_file.name}")

    print()

    # Step 2: Select CSV file
    while True:
        try:
            selection = input(
                f"Seleccione el archivo CSV (1-{len(csv_files)}): "
            ).strip()
            idx = int(selection) - 1
            if 0 <= idx < len(csv_files):
                selected_csv = csv_files[idx]
                break
            else:
                print(f"Por favor ingrese un número entre 1 y {len(csv_files)}")
        except ValueError:
            print("Por favor ingrese un número válido")

    file_dt = parse_filename_datetime(selected_csv.name)
    print()
    print(f"Archivo seleccionado: {selected_csv.name}")
    if file_dt:
        print(f"Fecha del archivo: {file_dt.strftime('%Y-%m-%d')}")
    print()

    # Step 3: Get time range
    print("Ingrese el rango de tiempo para subir datos:")
    print("Formato: HH:MM (ejemplo: 08:30)")
    print()

    while True:
        try:
            start_time_str = input("Hora inicio (HH:MM): ").strip()
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            break
        except ValueError:
            print("Formato inválido. Use HH:MM (ejemplo: 08:30)")

    while True:
        try:
            end_time_str = input("Hora fin (HH:MM): ").strip()
            end_time = datetime.strptime(end_time_str, "%H:%M").time()
            break
        except ValueError:
            print("Formato inválido. Use HH:MM (ejemplo: 17:45)")

    print()
    print(
        f"Rango seleccionado: {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
    )
    print()

    # Step 4: Confirm upload
    confirm = input(f"¿Confirmar subida de datos a InfluxDB? (si/no): ").strip().lower()

    if confirm not in ["si", "sí", "s", "yes", "y"]:
        print("Operación cancelada por el usuario.")
        sys.exit(0)

    # Step 5: Connect to InfluxDB and upload
    print()
    print(f"Conectando a InfluxDB: {INFLUX_CONFIG['url']}...")

    try:
        with InfluxDBClient(
            url=INFLUX_CONFIG["url"],
            token=INFLUX_CONFIG["token"],
            org=INFLUX_CONFIG["org"],
        ) as client:
            # Test connection
            health = client.health()
            if health.status != "pass":
                print(
                    f"ERROR: InfluxDB health check failed: {health.status}",
                    file=sys.stderr,
                )
                sys.exit(1)

            print("✓ Conectado a InfluxDB")
            print()

            # Upload CSV with time filtering
            total_points = upload_csv_with_time_filter(
                client, selected_csv, start_time, end_time, file_dt
            )

            print()
            print(f"=== Resumen ===")
            print(f"Archivo procesado: {selected_csv.name}")
            print(
                f"Rango de tiempo: {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
            )
            print(f"Puntos totales subidos: {total_points}")
            print(f"✓ Carga completada exitosamente")

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
