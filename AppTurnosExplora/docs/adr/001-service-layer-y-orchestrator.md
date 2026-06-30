# ADR 001: Service Layer y Patrón Orchestrator

**Estado:** Implementado  
**Fecha:** 2026-06

## Contexto

`procesar_solicitud.py` acumuló 638 líneas mezclando: extracción de datos del POST, validaciones, creación de solicitudes, y lógica específica por tipo. Era imposible testear en aislamiento y cualquier cambio requería entender todo el archivo.

## Decisión

Se extrajo la lógica a dos clases:

- **`SolicitudRequestParser`** — extrae y valida datos del POST, construye el dict `datos_solicitud`
- **`SolicitudOrchestrator`** — orquesta el flujo: sanción → restricción → receptor → parse → validar → crear

La vista quedó en 40 líneas: solo recibe HTTP, delega al orchestrator, devuelve respuesta.

## Consecuencias

- Tests unitarios posibles sobre Parser y Orchestrator sin simular requests HTTP
- Agregar un nuevo tipo de solicitud solo requiere tocar el Parser y la Strategy correspondiente
- La vista nunca crece por cambios de negocio
