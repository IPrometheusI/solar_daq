# source

Esta carpeta contiene el runtime principal del sistema DAQ. Aqui vive el proceso que `setup_repo.sh` instala y que `start_solar_daq.sh` ejecuta mediante `systemd`.

## Archivos

- `implementacion.py`: bucle principal de adquisicion. Lee INA228, ADS1115, DHT22, anemometro, pluviometro e irradiancia; guarda CSV diarios y recupera estado despues de reinicios.
- `influxdb_sender.py`: integracion opcional con InfluxDB. Inicializa la conexion, genera puntos y reintenta si la conexion falla.

## Flujo operativo

1. `bashScripts/start_solar_daq.sh` activa `.venv`.
2. Ejecuta `source/implementacion.py`.
3. El sistema escribe CSV en `/home/pi/Desktop/Mediciones`.
4. El estado de recuperacion se guarda en `/home/pi/Desktop/sensor_system_state.json` y `/home/pi/Desktop/sensor_system_state_backup.json`.

## Configuracion relevante

- Horario operativo actual: `05:00` a `18:00`.
- Direcciones INA228 esperadas: `0x40` y `0x41`.
- ADS1115 esperado en `0x48`.
- InfluxDB usa `INFLUX_URL`, `INFLUX_TOKEN`, `INFLUX_ORG` e `INFLUX_BUCKET`.

## Ejecucion manual

```bash
source .venv/bin/activate
python source/implementacion.py
```

En Raspberry Pi, `pigpiod` debe estar activo antes de iniciar el sistema:

```bash
sudo systemctl enable --now pigpiod
```
