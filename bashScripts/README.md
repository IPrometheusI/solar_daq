# bashScripts

Esta carpeta contiene los scripts auxiliares usados para arrancar, controlar y sincronizar el sistema Solar DAQ en la Raspberry Pi.

## Flujo actual
El arranque principal del sistema se hace con `start_solar_daq.sh`. Después de ejecutar `setup_repo.sh`, los scripts de esta carpeta se copian a `/home/pi/` y el servicio `solar_daq.service` usa `/home/pi/start_solar_daq.sh` para iniciar el software automáticamente al encender o reiniciar la Pi.

## Scripts

### `start_solar_daq.sh`
Lanzador principal del sistema.

- Resuelve la ruta real del repositorio.
- Activa el entorno virtual.
- Entra a `source/`.
- Ejecuta `implementacion.py`.
- Escribe eventos en `/home/pi/solar_daq.log`.

Uso manual:

```bash
/home/pi/start_solar_daq.sh
```

### `control_solar_daq.sh`
Panel de control en terminal, pensado para uso remoto por SSH o desde consola local.

Permite:
- ver `tail -f` del log
- revisar últimas líneas y errores
- iniciar, reiniciar o detener el sistema
- consultar estado general

Uso:

```bash
/home/pi/control_solar_daq.sh
```

### `sync_mediciones.sh`
Sincroniza los CSV de `/home/pi/Desktop/Mediciones` hacia Google Drive usando `rclone`.

Asume este remoto:

```bash
gdrive:Mediciones_RaspberryPi
```

Uso:

```bash
/home/pi/sync_mediciones.sh
```

Si quieres automatizar la sincronización, agrega una tarea en `crontab`:

```bash
crontab -e
```

Ejemplo, cada 5 minutos:

```cron
*/5 * * * * /home/pi/sync_mediciones.sh
```

### `resolve_project_root.sh`
Helper interno para encontrar la ruta real del repositorio aunque los scripts hayan sido copiados a `/home/pi`. No está pensado para ejecutarse directamente.
