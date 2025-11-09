# Sistema de Adquisición de Datos para Paneles Solares

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## Descripción del Proyecto
Este proyecto implementa un sistema completo de adquisición de datos (DAQ) para el monitoreo de variables eléctricas y ambientales de dos paneles solares. El sistema utiliza una **Raspberry Pi 4** como controlador principal y realiza mediciones cada minuto durante horario operativo (5:00 AM - 6:00 PM).

### Variables Monitoreadas

#### Variables Eléctricas (por panel)
- **Voltaje (V)** - Precisión de 4 decimales
- **Corriente (A)** - Precisión de 4 decimales  
- **Potencia (W)** - Precisión de 4 decimales
- **Energía (Wh)** - Acumulada diaria

#### Variables Ambientales
- **Irradiancia Solar (W/m²)** - Sensor Spektron 210
- **Temperatura** - 20 termistores distribuidos + DHT22
- **Humedad (%)** - Sensor DHT22
- **Velocidad del viento (m/s)** - Anemómetro
- **Dirección del viento** - Sensor resistivo
- **Precipitación (mm)** - Pluviómetro con resolución 0.2794 mm

## Objetivos
1. **Monitoreo continuo** de parámetros eléctricos y ambientales de paneles solares
2. **Almacenamiento local** de datos en formato CSV con sincronización automática a Google Drive
3. **Análisis de rendimiento** mediante correlación de variables eléctricas y ambientales
4. **Sistema robusto** con recuperación automática ante fallas y persistencia de estado

## Hardware Utilizado

### Controlador Principal
- **Raspberry Pi 4** - Procesador ARM Cortex-A72 quad-core 1.5GHz
- **Memoria interna** - Almacenamiento local (sin módulo SD)

### Sensores de Potencia
- **2x INA228** (Direcciones I2C: 0x40, 0x41) - Monitores de potencia de alta precisión
- **Shunt resistors**: 2mΩ cada uno
- **Corriente máxima**: 1.5A por canal

### Sensores Ambientales
- **ADS1115** (Dirección I2C: 0x48) - Conversor ADC 16-bit para sensores analógicos
- **Sensor de irradiancia Spektron 210** - Conexión diferencial al ADS1115
- **DHT22** - Sensor digital de temperatura y humedad
- **20 Termistores NTC** - Distribuidos en 3 multiplexores (CD74HC4051)
- **Anemómetro** - Sensor de efecto Hall (GPIO 23)
- **Pluviómetro** - Sensor de balancín magnético (GPIO 6)
- **Veleta** - Sensor resistivo para dirección del viento

### Componentes de Interfaz
- **3x Multiplexores CD74HC4051** - Expansión de canales analógicos
- **Resistencias de referencia** - 10kΩ para termistores

## Software y Arquitectura

### Plataforma de Desarrollo
- **Lenguaje**: Python 3.11
- **Sistema Operativo**: Raspberry Pi OS
- **Entorno virtual**: `venv` con dependencias aisladas

### Módulos Principales
- **implementacion.py** - Controlador principal y bucle de adquisición
- **ina228_monitor.py** - Monitor individual de sensores INA228
- **thermistor_monitor.py** - Gestión del array de termistores
- **irradiance_monitor.py** - Lectura del sensor de irradiancia
- **weather_kit_monitor.py** - Estación meteorológica completa
- **gauge.py** - Dashboard en tiempo real

### Librerías Principales
```
adafruit-circuitpython-ina228  # Sensores de potencia
adafruit-circuitpython-ads1x15 # Conversor ADC
adafruit-circuitpython-dht     # Sensor temperatura/humedad
RPi.GPIO                       # Control GPIO
gpiozero                       # Interfaz GPIO simplificada
```

### Sincronización en la Nube
- **Rclone** - Sincronización automática cada minuto a Google Drive
- **Carpeta local**: `/home/pi/Desktop/Mediciones/`
- **Carpeta remota**: `Mediciones_RaspberryPi` en Google Drive

## Funcionamiento del Sistema

### Ciclo de Operación
1. **Inicialización** (5:00 AM) - Creación de archivo CSV diario
2. **Adquisición continua** - Mediciones cada minuto
3. **Almacenamiento local** - Escritura inmediata a CSV
4. **Sincronización** - Upload automático a Google Drive vía Rclone
5. **Finalización** (6:00 PM) - Cierre de archivo y limpieza de estado

### Gestión de Estado
- **Persistencia** - Estado del sistema guardado en archivos JSON
- **Recuperación automática** - Continuación tras reinicios inesperados  
- **Validación de datos** - Verificación de integridad de archivos CSV
- **Manejo de errores** - Reinicialización automática tras fallas consecutivas

### Arquitectura Multi-hilo
- **Hilo principal** - Bucle de control y escritura de datos
- **Hilo de medición** - Lectura continua de sensores ambientales
- **Sincronización** - Mutex para acceso exclusivo al bus I2C

## Manual de Usuario

### Instalación y Configuración Inicial

#### 1. Preparación del Hardware
```bash
# Verificar conexiones según pinConfig.txt
# I2C: GPIO 2 (SDA), GPIO 3 (SCL)  
# MUX Control: GPIO 17, 27, 22
# DHT22: GPIO 5
# Anemómetro: GPIO 23
# Pluviómetro: GPIO 6
```

#### 2. Instalación del Software en Raspberry Pi
```bash
# Clonar repositorio
cd /home/pi/Desktop/
git clone <repository-url> solar_panels_daq

# Navegar al directorio de código
cd solar_panels_daq/Proyecto_2/Codigo_PI_4/

# Crear y activar entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

#### 2.1 Configuración de Credenciales InfluxDB
El código no incluye credenciales; el sistema busca las variables `SOLAR_DAQ_INFLUX_URL`, `SOLAR_DAQ_INFLUX_TOKEN`, `SOLAR_DAQ_INFLUX_ORG` y `SOLAR_DAQ_INFLUX_BUCKET`.

```bash
# Crear archivo local protegido (no versionar)
mkdir -p /home/pi/.config
nano /home/pi/.config/solar_daq.env
```

Contenido de ejemplo:

```
SOLAR_DAQ_INFLUX_URL=http://<host_influx>
SOLAR_DAQ_INFLUX_TOKEN=<token_privado>
SOLAR_DAQ_INFLUX_ORG=<organizacion>
SOLAR_DAQ_INFLUX_BUCKET=<bucket>
```

Guarda el archivo con permisos restringidos (`chmod 600`) y evita subirlo al repositorio.
El servicio leerá automáticamente este archivo; si usas otra ruta, define `SOLAR_DAQ_ENV_FILE=/ruta/deseada.env` antes de ejecutar los scripts.

#### 2.2 Setup Automatizado del Repositorio
El script `setup_repo.sh` automatiza la instalación de dependencias, el copiado de scripts y la creación del servicio systemd.

```bash
cd /home/pi/Desktop/DAQ
sudo bash setup_repo.sh
```

Este proceso ejecuta:
- Copia de `bashScripts/*.sh` a `/home/pi/` con permisos de ejecución.
- Instalación/actualización del entorno virtual en `./.venv` y de `requirements.txt`.
- Creación del servicio `solar_daq.service` (systemd) con ejecución al arranque y sin reinicio automático tras un `pkill` manual.

Puedes verificar su estado con:

```bash
systemctl status solar_daq.service
```

Para iniciar o detener el servicio manualmente:

```bash
sudo systemctl start solar_daq.service
sudo systemctl stop solar_daq.service
```

#### 3. Configuración de Scripts de Control
```bash
# Copiar scripts de bashContinue a /home/pi/
cd /home/pi/Desktop/solar_panels_daq/Proyecto_2/bashContinue/
cp *.sh /home/pi/
cd /home/pi/

# Hacer ejecutables
chmod +x *.sh
```

#### 4. Configuración de Rclone (Opcional)
```bash
# Configurar Rclone para Google Drive
rclone config

# Crear tarea cron para sincronización
crontab -e
# Añadir: */1 * * * * rclone copy /home/pi/Desktop/Mediciones/ gdrive:Mediciones_RaspberryPi/
```

### Operación del Sistema

#### Inicio del Sistema
```bash
# Opción 1: Inicio manual
cd /home/pi/Desktop/solar_panels_daq/Proyecto_2/Codigo_PI_4/
source venv/bin/activate
python implementacion.py

# Opción 2: Usando script de control
/home/pi/start_solar_daq.sh

# Opción 3: Inicio automático
/home/pi/start_daq_autostart.sh &
```

#### Panel de Control Interactivo
```bash
# Ejecutar panel de control
/home/pi/control_solar_daq.sh
```

**Opciones del Panel:**
- **Ver output en tiempo real** - Monitoreo live de mediciones
- **Ver últimas líneas** - Revisión rápida de estado  
- **Buscar errores** - Diagnóstico de problemas
- **Estadísticas** - Información de archivos de datos
- **Reiniciar/Detener** - Control del sistema

#### Monitoreo Individual de Sensores
```bash
cd /home/pi/Desktop/solar_panels_daq/Proyecto_2/Codigo_PI_4/
source venv/bin/activate

# Monitor de sensores INA228
python ina228_monitor.py

# Monitor de termistores  
python thermistor_monitor.py

# Monitor de irradiancia
python irradiance_monitor.py

# Estación meteorológica completa
python weather_kit_monitor.py

# Dashboard en tiempo real
python gauge.py
```

### Gestión de Datos

#### Estructura de Archivos
```
/home/pi/Desktop/Mediciones/
├── data_20241201_040000.csv  # Archivo diario
├── data_20241202_040000.csv
└── ...
```

#### Formato CSV
```
V0[V],V1[V],I0[A],I1[A],P0[W],P1[W],E0[Wh],E1[Wh],Irr[W/m2],
T0[°C],T1[°C],...,T19[°C],Rain[mm],Wind_Speed[m/s],Wind_Direction,
DHT_HUM[%],DHT_TEMP[°C],DateTime
```

#### Respaldo y Recuperación
- **Automático**: Sincronización a Google Drive cada minuto
- **Manual**: Copiar archivos desde `/home/pi/Desktop/Mediciones/`
- **Recuperación**: El sistema recupera estado automáticamente tras reinicios

### Resolución de Problemas

#### Problemas Comunes

**Sistema no inicia:**
```bash
# Verificar permisos
chmod +x /home/pi/*.sh

# Verificar entorno virtual
cd /home/pi/Desktop/solar_panels_daq/Proyecto_2/Codigo_PI_4/
source venv/bin/activate
python -c "import RPi.GPIO, adafruit_ina228"
```

**Sensores no responden:**
```bash
# Verificar conexiones I2C
i2cdetect -y 1

# Debe mostrar: 0x40, 0x41 (INA228), 0x48 (ADS1115)
```

**Archivos CSV no se crean:**
```bash
# Verificar directorio
mkdir -p /home/pi/Desktop/Mediciones/
chmod 755 /home/pi/Desktop/Mediciones/

# Verificar horario (sistema activo 5:00-18:00)
date
```

#### Logs del Sistema
```bash
# Log principal
tail -f /home/pi/implementacion_live_output.log

# Log de autostart
tail -f /home/pi/autostart_solar_daq.log

# Log del sistema
tail -f /home/pi/solar_daq.log
```

#### Reinicio Completo
```bash
# Detener procesos
pkill -f implementacion.py

# Limpiar GPIO
python3 -c "import RPi.GPIO; RPi.GPIO.cleanup()"

# Reiniciar sistema
/home/pi/start_solar_daq.sh
```

### Mantenimiento

#### Limpieza Periódica
```bash
# Limpiar logs antiguos (opcional)
find /home/pi/ -name "*.log" -mtime +7 -delete

# Verificar espacio en disco
df -h

# Sincronización manual con Google Drive
rclone sync /home/pi/Desktop/Mediciones/ gdrive:Mediciones_RaspberryPi/
```

#### Actualización del Sistema
```bash
cd /home/pi/Desktop/solar_panels_daq/
git pull origin main

# Reiniciar sistema tras actualizaciones
pkill -f implementacion.py
/home/pi/start_solar_daq.sh
```

### Especificaciones Técnicas

#### Precisión de Mediciones
- **Voltaje**: ±0.01% (INA228)
- **Corriente**: ±0.5% (INA228 + shunt 2mΩ)
- **Temperatura**: ±0.5°C (termistores NTC)
- **Irradiancia**: Calibración 1000W/m² = 75mV
- **Precipitación**: 0.2794 mm por pulso

#### Rangos de Operación
- **Voltaje**: 0-40V DC por canal
- **Corriente**: 0-1.5A por canal  
- **Temperatura**: -10°C a +70°C
- **Humedad**: 0-100% RH
- **Viento**: 0-50 m/s

#### Consumo de Energía
- **Raspberry Pi 4**: ~3W promedio
- **Sensores**: ~0.5W total
- **Sistema completo**: <4W

## Autor
Este proyecto fue desarrollado por **Maickol A. Fernández Obando** en el **Instituto Tecnológico de Costa Rica**, como parte del curso **EL-5617 Trabajo Final de Graduación**, para optar por el grado de **Licenciatura en Ingeniería Electrónica**.




## Cómo Citar este Trabajo

Si utilizas este software en tu investigación o proyecto, por favor cítalo usando el DOI de Zenodo:

```bibtex
@software{fernandez_obando_2024_solar_daq,
  author       = {Fernandez Obando, Maickol A.},
  title        = {Sistema de Adquisición de Datos para Paneles Solares},
  year         = 2024,
  publisher    = {Zenodo},
  version      = {v1.0.0},
  doi          = {10.5281/zenodo.XXXXXXX},
  url          = {https://doi.org/10.5281/zenodo.XXXXXXX}
}
```

También puedes citar directamente usando el archivo `CITATION.cff` incluido en este repositorio.

## Licencia

Este proyecto está licenciado bajo la **Licencia MIT** - ver el archivo [LICENSE](LICENSE) para más detalles.

Copyright (c) 2024 Maickol A. Fernandez Obando

## Contacto
Para cualquier consulta o colaboración, puedes contactar al autor a través del Instituto Tecnológico de Costa Rica.
