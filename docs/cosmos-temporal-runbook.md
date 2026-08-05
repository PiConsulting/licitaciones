# Runbook: Modos cosmos_temporal y cosmos_only

## Objetivo

Habilitar ejecucion productiva con Cosmos DB.

- `cosmos_temporal`: mantiene el flujo SQL como fallback y replica estado en Cosmos.
- `cosmos_only`: usa Cosmos para auth y ciclo de analisis (`create/start/status/cancel`) sin requerir PostgreSQL.

## Activacion

Variables requeridas:

- `APP_ENV=production`
- `USE_LOCAL_ADAPTERS=false`
- `PERSISTENCE_MODE=cosmos_temporal` o `PERSISTENCE_MODE=cosmos_only`
- `AZURE_BLOB_CONNECTION_STRING`
- `AZURE_BLOB_CONTAINER_NAME`
- `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`
- `AZURE_DOCUMENT_INTELLIGENCE_KEY`
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_KEY`
- `AZURE_SEARCH_INDEX_NAME`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`
- `AZURE_OPENAI_API_VERSION`
- `COSMOS_ENDPOINT`
- `COSMOS_KEY`
- `COSMOS_DATABASE`
- `COSMOS_CONTAINER`

## Estrategia de particionado

- Clave de particion usada por runtime: `analysis_id`.
- Cada item guardado incluye `partition_key=<analysis_id>`.
- Operaciones de lectura/escritura usan el mismo valor como partition key para minimizar costo y evitar cross-partition innecesario.

## Verificaciones operativas

1. Health:
   - `/health` debe devolver `checks.database.status = skipped` en `cosmos_temporal` y `cosmos_only`.
   - `checks.adapters.status` debe ser `ok`.
2. Crear analisis:
   - `POST /api/v1/analyses` crea estado draft y refleja metadata en Cosmos.
3. Iniciar analisis:
   - `POST /api/v1/analyses/{id}/start` cambia a queued.
4. Status:
   - `GET /api/v1/analyses/{id}/status` en `cosmos_temporal` prioriza snapshot runtime desde Cosmos.
   - en `cosmos_only` lee estado y versiones directamente desde Cosmos.
5. Cancelar:
   - `POST /api/v1/analyses/{id}/cancel` actualiza estado y replica evento en Cosmos.

## Seguridad

- No commitear secretos.
- Usar variables de entorno o secret manager.
- Recomendado para produccion: autenticacion AAD para Cosmos (`DefaultAzureCredential`) en lugar de key estatica.

## Rollback / salida a PostgreSQL

Cuando se habiliten credenciales Azure PostgreSQL:

1. Configurar `DATABASE_URL` de Azure PostgreSQL.
2. Elegir estrategia:
   - `PERSISTENCE_MODE=dual_write` para ventana de convivencia.
   - luego `PERSISTENCE_MODE=sql` como modo principal.
3. Reiniciar backend.
4. Verificar:
   - `/health` con check de DB en `ok`.
   - flujo completo de analisis y status sin desvio.
5. Mantener Cosmos como respaldo temporal hasta confirmar estabilidad.

## Checklist de conmutacion

- [ ] Variables cloud completas y validadas
- [ ] Health sin errores
- [ ] Flujo create/start/status/cancel verificado
- [ ] Logs con `correlation_id`
- [ ] Sin secretos en logs
- [ ] Pruebas backend en verde
