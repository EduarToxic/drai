# KB Pruebas RAG 2.0

## Importar el workflow en n8n
1. Inicia sesión en tu instancia de n8n y abre la vista de **Workflows**.
2. Haz clic en **Import from File** y selecciona el archivo `workflows/KB Pruebas RAG 2.0.json` de este repositorio.
3. Confirma la importación; verifica que las credenciales `Postgres DrAI` estén disponibles y que la variable `OPENAI_API_KEY` esté definida en el entorno de n8n.

## Probar consultas
1. Abre el workflow **KB Pruebas RAG 2.0** y pulsa **Execute Workflow** (Manual Trigger).
2. Ajusta el nodo **Set — Test Query** si quieres modificar la consulta de prueba.
3. Ejecuta el flujo con algunos ejemplos:
   - "Dolor abdominal 2 horas en F epigastrio, náuseas" (valor por defecto).
   - "Fiebre persistente con tos productiva en paciente de 65 años".
   - "Paciente pediátrico con erupción cutánea y fiebre alta".
4. Revisa el nodo **Return Data** para ver `rag_test.context_text`, `rag_test.citations` y/o el estado de error cuando aplique.
