# debugCodes

Esta carpeta agrupa scripts de diagnostico rapido para probar sensores por separado antes de correr el DAQ completo. Estan pensados para ejecutarse directamente en la Raspberry Pi, con el hardware ya conectado.

## Antes de usarlos

```bash
source .venv/bin/activate
sudo systemctl enable --now pigpiod
```

`pigpiod` es importante para los scripts que usan `gpiozero`.

## Scripts disponibles

- `ina228_monitor.py`: monitor en tiempo real para los dos INA228 (`0x40` y `0x41`). Muestra voltaje, corriente, potencia, energia y temperatura interna.
- `thermistor_monitor.py`: verifica `T0` a `T19` y tambien muestra DHT22. Usa el ADS1115 y el multiplexor.
- `irradiance_monitor.py`: prueba solo el canal de irradiancia y reporta mV y `W/m2`.
- `weather_kit_monitor.py`: integra viento, lluvia, direccion, DHT22 e irradiancia en una sola vista de diagnostico.
- `gauge.py`: solucionador interactivo para el pluviometro. Permite probar `RPi.GPIO`, `gpiozero` o polling manual.
- `test_influxdb.py`: envia datos simulados a InfluxDB usando `source/influxdb_sender.py`.

## Comandos utiles

```bash
python debugCodes/ina228_monitor.py
python debugCodes/thermistor_monitor.py
python debugCodes/irradiance_monitor.py
python debugCodes/weather_kit_monitor.py
python debugCodes/gauge.py
python debugCodes/test_influxdb.py
```

Para `test_influxdb.py`, primero define las variables de `.env.example`:

```bash
cp .env.example .env
set -a
source .env
set +a
python debugCodes/test_influxdb.py
```

Si un script falla, revisa primero `i2cdetect -y 1`, el estado de `pigpiod` y que no haya otro proceso ocupando los GPIO.
