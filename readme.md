# Proyecto HR-Analytics

Este es un proyecto integral de análisis de datos de Recursos Humanos. El alcance abarca desde la extracción de la fuente de datos original, el proceso de ETL (Extracción, Transformación y Carga), la creación de un dashboard interactivo para la visualización, hasta la comunicación estratégica de los insights obtenidos para la toma de decisiones.

---

## 🚀 Guía de Inicio Rápido

Sigue estos pasos para configurar el proyecto en tu entorno local.

### 1. Apertura de VS Code
Abre la aplicación **Visual Studio Code** en tu computadora. Si deseas abrirlo desde una carpeta específica, puedes navegar hasta ella en tu explorador de archivos, hacer clic derecho y seleccionar "Abrir con Code".

### 2. Apertura de la Terminal
Una vez dentro de VS Code, puedes abrir la terminal integrada de las siguientes maneras:
* Usa el atajo de teclado: `Ctrl + ñ` (en Windows) o `Cmd + J` (en Mac).
* Ve al menú superior en **Terminal** > **New Terminal**.

### 3. Clonar el Repositorio
Copia y pega el siguiente comando en la terminal para descargar el proyecto (reemplaza la URL si es necesario):

```bash
git clone https://github.com/dariomicheli/HR-Analytics
```
Nota: Después de clonar, entra a la carpeta del proyecto con: 
```bash
cd nombre-del-repo
```
### 4. Creación del Entorno Virtual
Es recomendable usar un entorno virtual para mantener las librerías aisladas:

```bash
# Crear el entorno (llamado 'env')
python -m venv env

# Activar el entorno
# En Windows:
source env/Scripts/activate
```
### 5. Instalación de Librerías
Una vez activado el entorno, instala todas las dependencias necesarias con el siguiente comando:

```bash
pip install -r requirements.txt
```
---

### 🔄Flujo de Trabajo con Git
Utiliza estos comandos para mantener tu código sincronizado.

#### Traer actualizaciones (Download)
Para actualizar tu copia local con los cambios que otros hayan subido al repositorio remoto:
```bash
git pull origin main
```

#### Subir tus cambios (Upload)
Para guardar y enviar tus avances al repositorio remoto, sigue este orden de comandos:

Preparar los archivos:

```bash
git add .
```
#### Crear el punto de restauración (Commit):

```bash
git commit -m "Descripción breve de los cambios realizados"
```
#### Enviar al servidor:

```bash
git push origin main
```