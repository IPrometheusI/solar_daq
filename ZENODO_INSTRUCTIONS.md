# Guía para Publicar en Zenodo

Esta guía te ayudará a publicar tu repositorio en Zenodo para obtener un DOI citable.

## Preparación del Repositorio (Ya completado ✓)

Tu repositorio ya está listo con:
- ✅ Licencia MIT (`LICENSE`)
- ✅ Archivo de metadatos Zenodo (`.zenodo.json`)
- ✅ Archivo de citación estándar (`CITATION.cff`)
- ✅ Archivo `.gitignore` configurado
- ✅ Herramientas de linting configuradas
- ✅ README actualizado con badges

## Pasos para Publicar en Zenodo

### 1. Asegúrate de que el Repositorio esté en GitHub

Si aún no lo has hecho:

```bash
# Asegúrate de que todo esté commiteado
git add .
git commit -m "Preparación para publicación en Zenodo"

# Si no has creado el repositorio remoto, créalo en GitHub y luego:
git remote add origin https://github.com/TU_USUARIO/TU_REPOSITORIO.git
git push -u origin main
```

### 2. Conectar GitHub con Zenodo

1. Ve a [https://zenodo.org/](https://zenodo.org/)
2. Haz clic en **"Sign up"** o **"Log in"**
3. Selecciona **"Log in with GitHub"** (esto permite la integración)
4. Autoriza a Zenodo para acceder a tu cuenta de GitHub

### 3. Habilitar el Repositorio en Zenodo

1. Una vez autenticado, ve a tu perfil en Zenodo
2. Haz clic en **"GitHub"** en el menú superior
3. Busca tu repositorio en la lista
4. **Activa el switch** junto al nombre de tu repositorio
   - Si no aparece, haz clic en "Sync now" para actualizar la lista

### 4. Crear un Release en GitHub

Zenodo solo archiva **releases** de GitHub, no commits individuales:

```bash
# Opción 1: Desde la línea de comandos
git tag -a v1.0.0 -m "Primera versión publicable para Zenodo"
git push origin v1.0.0
```

**Opción 2: Desde la interfaz web de GitHub:**
1. Ve a tu repositorio en GitHub
2. Haz clic en **"Releases"** → **"Create a new release"**
3. En "Tag version" escribe: `v1.0.0`
4. En "Release title" escribe: `v1.0.0 - Primera versión publicable`
5. Describe los cambios en la descripción
6. Haz clic en **"Publish release"**

### 5. Verificar la Publicación en Zenodo

1. Espera unos minutos (normalmente 5-10 min)
2. Ve a [https://zenodo.org/account/settings/github/](https://zenodo.org/account/settings/github/)
3. Deberías ver tu repositorio con un DOI asignado
4. Haz clic en el DOI para ver la página de tu publicación

### 6. Actualizar el DOI en tu Repositorio

Una vez que tengas el DOI (será algo como `10.5281/zenodo.1234567`):

1. **Actualiza `.zenodo.json`:**
   - Cambia `YOUR_PAPER_DOI_HERE` por el DOI de tu paper (si lo tienes)

2. **Actualiza `README.md`:**
   - Reemplaza `10.5281/zenodo.XXXXXXX` con tu DOI real en los badges
   - Actualiza la cita BibTeX con el DOI correcto

3. **Actualiza `CITATION.cff`:**
   - Agrega el DOI al archivo (si deseas)

4. **Commit y push:**
```bash
git add .
git commit -m "Actualizar DOI de Zenodo"
git push origin main
```

### 7. (Opcional) Crear un Nuevo Release con el DOI Actualizado

Si quieres que la versión con el DOI correcto también esté archivada:

```bash
git tag -a v1.0.1 -m "Versión con DOI actualizado"
git push origin v1.0.1
```

## Formato del Badge de Zenodo

El badge de Zenodo en tu README se verá así:
```markdown
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.TU_DOI.svg)](https://doi.org/10.5281/zenodo.TU_DOI)
```

## Notas Importantes

1. **Cada release genera un nuevo DOI:** Zenodo crea un DOI único para cada versión, más un "DOI conceptual" que apunta siempre a la última versión
2. **Usa el DOI conceptual en papers:** Es mejor usar el DOI conceptual en publicaciones para que siempre apunte a la última versión
3. **Los metadatos en `.zenodo.json`** se usan automáticamente al crear el registro en Zenodo
4. **Privacidad:** Puedes hacer el repositorio privado en Zenodo si lo deseas (no recomendado para Open Source)

## Verificación de Calidad del Código

Antes de publicar, considera ejecutar los linters:

```bash
# Instalar herramientas de desarrollo
pip install black isort flake8

# Formatear código
black source/ debugCodes/
isort source/ debugCodes/

# Verificar estilo
flake8 source/ debugCodes/
```

## Recursos Adicionales

- [Documentación oficial de Zenodo-GitHub](https://docs.github.com/en/repositories/archiving-a-github-repository/referencing-and-citing-content)
- [Guía de Zenodo](https://help.zenodo.org/)
- [Making Your Code Citable](https://guides.github.com/activities/citable-code/)

## Contacto y Soporte

Si tienes problemas con Zenodo:
- Email de soporte: [support@zenodo.org](mailto:support@zenodo.org)
- Foro de Zenodo: [https://github.com/zenodo/zenodo/discussions](https://github.com/zenodo/zenodo/discussions)
