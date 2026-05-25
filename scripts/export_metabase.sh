#!/bin/bash

# Nombre del contenedor de la base de datos de Metabase
CONTAINER_NAME="postgres-metabase"
OUTPUT_FILE="./sql/init_metabase.sql"

echo "=================================================="
echo "🔄 Automatización: Exportando metadata de Metabase..."
echo "=================================================="

# Comprobamos si el contenedor está corriendo
if [ "$(docker inspect -f '{{.State.Running}}' $CONTAINER_NAME 2>/dev/null)" = "true" ]; then
    # Ejecuta el dump y sobreescribe el archivo .sql
    docker exec -t $CONTAINER_NAME pg_dump -U metabase metabase > $OUTPUT_FILE
    
    # Agrega automáticamente el archivo actualizado al commit actual
    git add $OUTPUT_FILE
    echo "✅ ¡Dashboards exportados exitosamente en $OUTPUT_FILE y añadidos al commit!"
else
    echo "⚠️ El contenedor $CONTAINER_NAME no está corriendo."
    echo "❌ No se pudieron guardar los últimos cambios de Metabase en el .sql."
    echo "💡 Recordá tener Docker levantado si modificaste los dashboards."
fi
echo "=================================================="