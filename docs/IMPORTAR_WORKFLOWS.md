# Importar workflows de DrAI en n8n

Este repositorio contiene los flujos exportados de n8n que soportan DrAI. Sigue estos pasos para cargarlos en una instancia nueva y dejar las credenciales listas.

## 1. Preparar variables de entorno

1. Copia el archivo `.env.example` y ajusta las claves necesarias:
   ```bash
   cp .env.example .env
   ```
2. Completa los valores que usará n8n (por ejemplo `OPENAI_API_KEY`).
3. Si ejecutas n8n en Docker, referencia el archivo mediante [`env_file`](https://docs.docker.com/compose/environment-variables/set-environment-variables/#use-the-env_file-attribute):
   ```yaml
   services:
     n8n:
       image: n8nio/n8n
       env_file:
         - ./n8n/.env
   ```
4. Para despliegues sin Docker puedes cargar las variables con `source .env` antes de iniciar el proceso o configurarlas en el gestor de servicios correspondiente.

## 2. Importar los workflows

1. Ingresa al panel de n8n con una cuenta con permisos de edición.
2. En la barra lateral elige **Workflows → Import**.
3. Selecciona el archivo JSON desde la carpeta `workflows/` de este repo y confirma la importación.
4. Repite el proceso para cada flujo que necesites (`DrAI`, `KB Ingest Sources`, `KB Pruebas RAG`, etc.).

## 3. Revisar credenciales

Después de importar:

- Abre **Credentials** y vincula las conexiones que requieren claves (por ejemplo PostgreSQL, Telegram o credenciales HTTP).
- Confirma que las variables utilizadas en cabeceras (`Bearer {{$env.OPENAI_API_KEY}}`) estén presentes en el entorno.

## 4. Dependencias recomendadas

El flujo `KB Ingest Sources` espera que en el host estén instalados:

- [`pdftotext`](https://poppler.freedesktop.org/) (`poppler-utils`) para extraer texto paginado.
- Una herramienta de OCR (por ejemplo `ocrmypdf`) para manejar PDFs escaneados. Los nodos marcarán `chunk_warning` cuando detecten que falta texto.

Mantén estos paquetes disponibles en la imagen/host donde corre n8n para evitar fallas en el proceso de chunking.
