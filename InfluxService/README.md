# InfluxService

Herramientas de utilidad para gestionar datos en InfluxDB del sistema de adquisición de datos solar.

## Descripción

Esta carpeta contiene scripts de Python para realizar operaciones de mantenimiento y recuperación de datos en la base de datos InfluxDB:

- **Subir datos históricos desde archivos CSV**
- **Eliminar datos en rangos de tiempo específicos**

Ambos scripts están diseñados para trabajar con la zona horaria de Costa Rica (`America/Costa_Rica`) y convertir automáticamente a UTC para InfluxDB.

---

## Archivos

### 1. `upload_csv_to_influx.py`

**Propósito**: Subir datos históricos desde archivos CSV a InfluxDB con filtrado por rango de tiempo.

**Uso típico**:
- Recuperar datos perdidos por problemas de conectividad
- Migrar datos históricos a InfluxDB
- Re-subir datos específicos de ciertos períodos

#### Características

- ✅ Lectura automática de archivos CSV desde `archivos_csv/`
- ✅ Filtrado por rango de tiempo (hora inicio - hora fin)
- ✅ Conversión automática de timezone CR → UTC
- ✅ Manejo de BOM UTF-8
- ✅ Mapeo completo de todos los campos del CSV a InfluxDB
- ✅ Validación de datos antes de subir
- ✅ Contador de puntos subidos y omitidos

#### Formato de archivos CSV esperado

```
data_YYYYMMDD_HHMMSS.csv
```

Ejemplo: `data_20251018_083000.csv`

#### Estructura del CSV

El CSV debe contener las siguientes columnas:

**Columnas principales:**
- `V0[V]`, `V1[V]` - Voltaje paneles 1 y 2
- `I0[A]`, `I1[A]` - Corriente paneles 1 y 2
- `P0[W]`, `P1[W]` - Potencia paneles 1 y 2
- `E0[Wh]`, `E1[Wh]` - Energía acumulada paneles 1 y 2
- `Irr[W/m2]` - Irradiancia
- `Rain[mm]` - Lluvia acumulada
- `Wind_Speed[m/s]` - Velocidad del viento
- `Wind_Direction` - Dirección del viento (formato: `90.0°(E)`)
- `DHT_HUM[%]` - Humedad ambiente
- `DHT_TEMP[°C]` - Temperatura ambiente

**Termistores:**
- `T0[°C]` a `T19[°C]` - 20 sensores de temperatura

**Timestamp:**
- `DateTime` - Formato: `YYYY-MM-DD HH:MM:SS` (hora local CR)

#### Mapeo a InfluxDB

| Columna CSV | Field InfluxDB | Tipo |
|-------------|----------------|------|
| V0[V] | panel1_voltage | float |
| V1[V] | panel2_voltage | float |
| I0[A] | panel1_current | float |
| I1[A] | panel2_current | float |
| P0[W] | panel1_power | float |
| P1[W] | panel2_power | float |
| E0[Wh] | panel1_energy | float |
| E1[Wh] | panel2_energy | float |
| Irr[W/m2] | irradiance | float |
| Rain[mm] | rain_accumulation | float |
| Wind_Speed[m/s] | wind_speed | float |
| Wind_Direction | wind_direction | float (solo grados) |
| DHT_HUM[%] | ambient_humidity | float |
| DHT_TEMP[°C] | ambient_temperature | float |
| T0[°C] - T19[°C] | thermistor_00_temp - thermistor_19_temp | float |

**Tags adicionales:**
- `system`: `raspberry_pi`
- `location`: `solar_farm`

**Measurement**: `solar_panel_measurement`

#### Cómo usar

1. **Asegúrate de tener archivos CSV en la carpeta `archivos_csv/`**

2. **Ejecuta el script:**
   ```bash
   python upload_csv_to_influx.py
   ```

3. **Sigue las instrucciones interactivas:**
   ```
   === CSV to InfluxDB Uploader ===

   Archivos CSV disponibles:
     1. data_20251018_083000.csv - 2025-10-18 08:30:00
     2. data_20251019_083000.csv - 2025-10-19 08:30:00

   Seleccione el archivo CSV (1-2): 1

   Archivo seleccionado: data_20251018_083000.csv
   Fecha del archivo: 2025-10-18

   Ingrese el rango de tiempo para subir datos:
   Formato: HH:MM (ejemplo: 08:30)

   Hora inicio (HH:MM): 08:30
   Hora fin (HH:MM): 17:45

   Rango seleccionado: 08:30 - 17:45

   ¿Confirmar subida de datos a InfluxDB? (si/no): si
   ```

4. **El script mostrará el progreso:**
   ```
   Conectando a InfluxDB: http://influx.agrivoltaic.ecaslab.org...
   ✓ Conectado a InfluxDB

   ✓ Uploaded 558 points from data_20251018_083000.csv
     Skipped 0 points outside time range

   === Resumen ===
   Archivo procesado: data_20251018_083000.csv
   Rango de tiempo: 08:30 - 17:45
   Puntos totales subidos: 558
   ✓ Carga completada exitosamente
   ```

#### Casos especiales

**Rangos que cruzan medianoche:**

El script maneja correctamente rangos de tiempo que cruzan la medianoche:

```
Hora inicio (HH:MM): 23:00
Hora fin (HH:MM): 02:00
```

Esto subirá datos desde las 23:00 hasta las 02:00 del día siguiente.

**Valores N/A o inválidos:**

El script omite automáticamente valores que son:
- Vacíos
- "N/A"
- NaN
- No numéricos

---

### 2. `delete_influx_range.py`

**Propósito**: Eliminar datos de InfluxDB en un rango de tiempo específico.

**Uso típico**:
- Eliminar datos corruptos o erróneos
- Limpiar datos de pruebas
- Corregir datos duplicados

#### Características

- ✅ Conversión automática de hora local CR a UTC
- ✅ Previsualización de puntos a eliminar antes de confirmar
- ✅ Confirmación explícita requerida (escribir "DELETE")
- ✅ Validación de formato de fecha y hora
- ✅ Soporte para filtrado por tags (opcional)

#### Cómo usar

1. **Ejecuta el script:**
   ```bash
   python delete_influx_range.py
   ```

2. **Sigue las instrucciones interactivas:**
   ```
   === Delete InfluxDB Data ===

   Ingrese los datos para eliminar:

   Fecha (YYYY-MM-DD, ejemplo: 2025-10-18): 2025-10-18
   Hora inicio (HH:MM, ejemplo: 08:30): 08:30
   Hora fin (HH:MM, ejemplo: 17:45): 17:45

   === Plan de Eliminación ===
    URL        : http://influx.agrivoltaic.ecaslab.org
    Org        : agrivoltaic
    Bucket     : daq
    Measurement: solar_panel_measurement
    Tags       : (none)
    Local CR   : 2025-10-18 08:30 -> 17:45
    UTC Window : 2025-10-18T14:30:00Z -> 2025-10-18T23:45:00Z  (stop is exclusive)
    Predicate  : _measurement="solar_panel_measurement"
   ============================

   Puntos encontrados que coinciden: 558

   ¿Confirmar eliminación de estos datos? Escriba 'DELETE' para confirmar: DELETE

   ✅ Solicitud de eliminación completada exitosamente.
   ```

#### ⚠️ Advertencias importantes

1. **La eliminación es IRREVERSIBLE** - Los datos no se pueden recuperar después de eliminar
2. **Debes escribir exactamente "DELETE"** en mayúsculas para confirmar
3. **El tiempo de fin (stop) es EXCLUSIVO** - Los datos en ese momento exacto NO se eliminan
4. **Verifica siempre el preview** antes de confirmar

#### Funcionamiento técnico

El script utiliza la **InfluxDB Delete API** que tiene las siguientes limitaciones:

- ✅ Puede filtrar por `_measurement`
- ✅ Puede filtrar por tags
- ❌ **NO puede filtrar por fields** (_field)

Esto significa que eliminará **todos los fields** que coincidan con el measurement y tags en el rango de tiempo especificado.

---

## Requisitos

### Dependencias Python

Ambos scripts requieren las siguientes dependencias:

```bash
pip install influxdb-client
```

Para Python < 3.9, también necesitas:

```bash
pip install backports.zoneinfo
```

### Python versión

- **Recomendado**: Python 3.9 o superior (soporte nativo de zoneinfo)
- **Mínimo**: Python 3.7 (requiere backports.zoneinfo)

### Configuración de InfluxDB

Los scripts usan la siguiente configuración (definida en ambos archivos):

```python
INFLUX_CONFIG = {
    "url": "http://influx.agrivoltaic.ecaslab.org",
    "token": "hzT2Yc4Vv44bW6ruNntzxgBIzBaJDlTJfhlWZK-WPpHahsV395-4cUbyo8c8j6iIgbwaHT7HwtN_wrS8C9WGtg==",
    "org": "agrivoltaic",
    "bucket": "daq",
}
```

**Nota de seguridad**: En producción, considera mover el token a variables de entorno:

```python
import os
INFLUX_CONFIG = {
    "token": os.getenv("INFLUX_TOKEN"),
    # ...
}
```

---

## Zona Horaria

**Importante**: Ambos scripts trabajan con la zona horaria de **Costa Rica** (`America/Costa_Rica`).

- **Entrada del usuario**: Hora local de Costa Rica
- **Conversión automática**: Los scripts convierten a UTC para InfluxDB
- **UTC offset**: Costa Rica = UTC-6 (sin cambio de horario de verano)

### Ejemplo de conversión:

```
Local CR: 2025-10-18 08:30
UTC:      2025-10-18 14:30
```

---

## Estructura de directorios esperada

```
solar_daq/
├── InfluxService/
│   ├── README.md                    # Este archivo
│   ├── upload_csv_to_influx.py     # Subir CSVs
│   └── delete_influx_range.py      # Eliminar datos
├── archivos_csv/                    # Carpeta de CSVs (para upload)
│   ├── data_20251018_083000.csv
│   ├── data_20251019_083000.csv
│   └── ...
└── source/
    ├── implementacion.py            # Sistema principal
    └── influxdb_sender.py          # Envío en tiempo real
```

---

## Flujo de trabajo común

### Escenario 1: Recuperar datos perdidos

1. **Identifica el período sin datos** en InfluxDB
2. **Localiza el archivo CSV correspondiente** en `archivos_csv/`
3. **Ejecuta `upload_csv_to_influx.py`**
4. **Selecciona el archivo y rango de tiempo**
5. **Confirma la subida**

### Escenario 2: Corregir datos erróneos

1. **Identifica el rango de datos incorrectos**
2. **Ejecuta `delete_influx_range.py`**
3. **Especifica fecha y rango de tiempo**
4. **Verifica el preview de puntos a eliminar**
5. **Confirma con "DELETE"**
6. **Re-sube los datos correctos** con `upload_csv_to_influx.py`

### Escenario 3: Datos duplicados

1. **Identifica el rango duplicado**
2. **Ejecuta `delete_influx_range.py`** para eliminar todos los datos del rango
3. **Ejecuta `upload_csv_to_influx.py`** para re-subir los datos correctos una sola vez

---

## Troubleshooting

### Error: "Module 'zoneinfo' not found"

**Solución**:
```bash
pip install backports.zoneinfo
```

### Error: "Module 'influxdb_client' not found"

**Solución**:
```bash
pip install influxdb-client
```

### Error: "Folder 'archivos_csv' does not exist"

**Solución**: Crea la carpeta o ajusta la ruta en el script:
```bash
mkdir archivos_csv
```

O modifica la constante:
```python
CSV_FOLDER = "ruta/a/tus/csvs"
```

### InfluxDB health check failed

**Posibles causas**:
- Servidor InfluxDB no disponible
- Token inválido o expirado
- Problemas de red/firewall

**Solución**:
```bash
# Verifica conectividad
ping influx.agrivoltaic.ecaslab.org

# Verifica el servidor InfluxDB está corriendo
curl http://influx.agrivoltaic.ecaslab.org/health
```

### Puntos encontrados: 0 (pero debería haber datos)

**Posibles causas**:
- Rango de tiempo incorrecto
- Measurement name diferente
- Datos ya fueron eliminados

**Solución**: Verifica con una query Flux en InfluxDB UI:
```flux
from(bucket: "daq")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "solar_panel_measurement")
  |> limit(n: 10)
```

---

## Advertencias de seguridad

⚠️ **Token de acceso**: Los scripts contienen el token de InfluxDB en texto plano. En producción:
- Usa variables de entorno
- Restringe permisos del archivo
- No subas el token a repositorios públicos

⚠️ **Permisos del token**: Asegúrate de que el token tiene:
- Permiso de **escritura** (write) para `upload_csv_to_influx.py`
- Permiso de **eliminación** (delete) para `delete_influx_range.py`
- Permiso de **lectura** (read) para preview queries

---

## Funciones documentadas

Cada función en los scripts está documentada siguiendo el formato:

```python
###################################
# nombre_funcion
# Argumentos:
#   - parametro1 (tipo): Descripción
#   - parametro2 (tipo): Descripción
# Return: tipo - Descripción del valor de retorno
# Descripcion: Descripción detallada de la función
###################################
```

Para más detalles, consulta directamente los archivos de código fuente.

---

## Contacto y soporte

Para problemas o preguntas sobre estos scripts, contacta al equipo de desarrollo del sistema de adquisición de datos solar.

---

**Última actualización**: 2025-12-04
