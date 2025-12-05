# Configuración del Sistema

Este documento explica cómo configurar las credenciales de InfluxDB para el sistema de adquisición de datos solar.

## ⚠️ Importante - Seguridad

**NUNCA** subas archivos con credenciales reales a repositorios públicos. Las credenciales deben configurarse mediante variables de entorno o archivos `.env` locales.

---

## Método 1: Variables de entorno (Recomendado para producción)

### En Linux/macOS (Raspberry Pi)

1. **Edita el archivo de perfil de tu shell:**

   ```bash
   nano ~/.bashrc
   # o si usas zsh:
   nano ~/.zshrc
   ```

2. **Agrega al final del archivo:**

   ```bash
   # InfluxDB Configuration
   export INFLUX_URL="http://tu-servidor-influxdb.com"
   export INFLUX_TOKEN="tu-token-de-influxdb-aqui"
   export INFLUX_ORG="tu-organizacion"
   export INFLUX_BUCKET="tu-bucket"
   ```

3. **Recarga el archivo de configuración:**

   ```bash
   source ~/.bashrc
   # o si usas zsh:
   source ~/.zshrc
   ```

4. **Verifica que las variables estén configuradas:**

   ```bash
   echo $INFLUX_URL
   echo $INFLUX_TOKEN
   ```

### En Windows (PowerShell)

1. **Configura las variables de entorno del sistema:**

   ```powershell
   [System.Environment]::SetEnvironmentVariable('INFLUX_URL', 'http://tu-servidor-influxdb.com', 'User')
   [System.Environment]::SetEnvironmentVariable('INFLUX_TOKEN', 'tu-token-de-influxdb-aqui', 'User')
   [System.Environment]::SetEnvironmentVariable('INFLUX_ORG', 'tu-organizacion', 'User')
   [System.Environment]::SetEnvironmentVariable('INFLUX_BUCKET', 'tu-bucket', 'User')
   ```

2. **Reinicia PowerShell** para que las variables tomen efecto.

---

## Método 2: Archivo .env (Para desarrollo local)

1. **Copia el archivo de ejemplo:**

   ```bash
   cp .env.example .env
   ```

2. **Edita el archivo `.env` con tus credenciales:**

   ```bash
   nano .env
   ```

   ```env
   # InfluxDB Configuration
   INFLUX_URL=http://tu-servidor-influxdb.com
   INFLUX_TOKEN=tu-token-de-influxdb-aqui
   INFLUX_ORG=tu-organizacion
   INFLUX_BUCKET=tu-bucket
   ```

3. **Instala python-dotenv (si no está instalado):**

   ```bash
   pip install python-dotenv
   ```

4. **Modifica los scripts para cargar el archivo `.env`** (solo necesario si usas este método):

   Al inicio de cada script Python, agrega:

   ```python
   from dotenv import load_dotenv
   load_dotenv()  # Carga variables de .env
   ```

**Nota**: El archivo `.env` ya está en `.gitignore` y NO será subido al repositorio.

---

## Método 3: Editar directamente en el código (NO recomendado)

Solo para pruebas locales. **NO subir al repositorio con credenciales reales.**

Edita los valores directos en los archivos:

- `source/influxdb_sender.py`
- `InfluxService/delete_influx_range.py`
- `InfluxService/upload_csv_to_influx.py`

```python
INFLUX_CONFIG = {
    "url": "http://tu-servidor-influxdb.com",
    "token": "tu-token-de-influxdb-aqui",
    "org": "tu-organizacion",
    "bucket": "tu-bucket",
}
```

---

## Cómo obtener las credenciales de InfluxDB

### 1. URL del servidor

Es la dirección donde está alojado tu servidor InfluxDB.

**Ejemplo**: `http://influx.ejemplo.com` o `http://192.168.1.100:8086`

### 2. Token de acceso

1. Accede a la interfaz web de InfluxDB
2. Ve a **Data** → **API Tokens** (o **Load Data** → **Tokens**)
3. Copia un token existente o crea uno nuevo con los permisos necesarios:
   - **Read** access al bucket (para queries)
   - **Write** access al bucket (para escribir datos)
   - **Delete** access al bucket (para eliminar datos)

### 3. Organización (Org)

El nombre de tu organización en InfluxDB.

Puedes verlo en la interfaz web, generalmente en la esquina superior izquierda.

### 4. Bucket

El nombre del bucket (base de datos) donde se almacenan los datos.

Puedes verlo en **Data** → **Buckets** en la interfaz web de InfluxDB.

---

## Verificar la configuración

### Para el sistema principal (implementacion.py)

1. **Ejecuta el sistema:**

   ```bash
   cd source
   python implementacion.py
   ```

2. **Verifica el log de inicio**. Deberías ver:

   ```
   ✓ Conexión a InfluxDB establecida
   ```

   Si ves errores de conexión, verifica tus credenciales.

### Para los scripts de InfluxService

1. **Prueba la conexión:**

   ```bash
   cd InfluxService
   python upload_csv_to_influx.py
   ```

2. **Deberías ver:**

   ```
   Conectando a InfluxDB: http://tu-servidor...
   ✓ Conectado a InfluxDB
   ```

---

## Troubleshooting

### Error: "INFLUX_TOKEN environment variable not set"

**Solución**: Asegúrate de haber configurado las variables de entorno correctamente.

Verifica con:
```bash
echo $INFLUX_TOKEN
```

### Error: "Connection refused" o "Timeout"

**Posibles causas**:
- URL incorrecta
- Servidor InfluxDB no está corriendo
- Firewall bloqueando la conexión
- Problemas de red

**Solución**: Verifica la conectividad:
```bash
ping tu-servidor-influxdb.com
curl http://tu-servidor-influxdb.com/health
```

### Error: "Unauthorized" o "Invalid token"

**Posibles causas**:
- Token incorrecto
- Token expirado
- Permisos insuficientes

**Solución**: Verifica/regenera el token en la interfaz web de InfluxDB.

### Error: "Bucket not found"

**Posibles causas**:
- Nombre del bucket incorrecto
- Bucket no existe en la organización especificada

**Solución**: Verifica el nombre del bucket en InfluxDB UI.

---

## Configuración para inicio automático (Raspberry Pi)

Si quieres que el sistema inicie automáticamente con las variables de entorno:

### Usando systemd (Recomendado)

1. **Crea un archivo de servicio:**

   ```bash
   sudo nano /etc/systemd/system/solar-daq.service
   ```

2. **Contenido del archivo:**

   ```ini
   [Unit]
   Description=Solar DAQ System
   After=network.target

   [Service]
   Type=simple
   User=pi
   WorkingDirectory=/home/pi/solar_daq/source
   Environment="INFLUX_URL=http://tu-servidor-influxdb.com"
   Environment="INFLUX_TOKEN=tu-token-aqui"
   Environment="INFLUX_ORG=tu-organizacion"
   Environment="INFLUX_BUCKET=tu-bucket"
   ExecStart=/usr/bin/python3 /home/pi/solar_daq/source/implementacion.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

3. **Habilita e inicia el servicio:**

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable solar-daq.service
   sudo systemctl start solar-daq.service
   ```

4. **Verifica el estado:**

   ```bash
   sudo systemctl status solar-daq.service
   ```

---

## Archivos que contienen configuración de InfluxDB

Los siguientes archivos necesitan las credenciales configuradas:

1. ✅ `source/influxdb_sender.py` - Sistema principal de envío en tiempo real
2. ✅ `InfluxService/upload_csv_to_influx.py` - Subir datos históricos
3. ✅ `InfluxService/delete_influx_range.py` - Eliminar datos

Todos usan las mismas variables de entorno, por lo que solo necesitas configurarlas una vez.

---

## Seguridad - Lista de verificación

- [ ] Las credenciales están en variables de entorno o archivo `.env`
- [ ] El archivo `.env` NO está en el repositorio git
- [ ] El archivo `.env` está en `.gitignore`
- [ ] No hay tokens hardcodeados en archivos Python
- [ ] Los tokens tienen solo los permisos necesarios
- [ ] Las credenciales se guardan de forma segura (no en texto plano en lugares públicos)

---

**Última actualización**: 2025-12-04
