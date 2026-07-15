# Contexto del proyecto — Rosati Motors · Lead Intelligence (BANT)

Guía para agentes de código (Codex, Claude Code, etc.) que trabajen en este repo.
Última actualización: 2026-07-15.

## Qué es este proyecto

Implementación del sistema descrito en `prompt-calificacion-leads-BANT-RosatiMotors (2).md`
(el documento de especificación original — **no editarlo**, es la fuente de requisitos).
Rosati Motors es un concesionario de ultra-lujo en Ecuador (Lamborghini, Maserati, McLaren).
La app recibe leads de Instagram/Facebook Ads o formulario web, los califica con metodología
BANT (Claude), los persiste en PostgreSQL (SQLite local) y los enruta al equipo comercial. Incluye una interfaz
web completa (panel, pipeline, expediente, calificación en vivo) con tema oscuro de lujo
automotriz, pensada para demos con clientes y desplegada en Railway.

## Arquitectura y archivos

| Archivo | Rol |
|---|---|
| `prompt_sistema.md` | Prompt de sistema BANT para Claude. Editable por negocio sin tocar código. |
| `clasificador.py` | `clasificar_lead(dict) -> CalificacionLead`. SDK `anthropic`, `client.messages.parse()` + `output_format=<Pydantic>` (structured outputs). Modelo `claude-opus-4-8`, thinking adaptativo. Lanza `RuntimeError` si `parsed_output` es None (refusal). |
| `simulador.py` | `calificar_simulado(dict)` — heurística transparente para demo sin API key, y `asignacion_crm(clasificacion)` — mapeo único clasificación → asesor/etapa/SLA. |
| `clickup.py` | Integración resiliente: crea tareas HOT/WARM, reparte entre `CLICKUP_ASSIGNEES` (round-robin o todos), aplica prioridad y SLA; COLD/DESCARTAR se omiten. |
| `db.py` | PostgreSQL/SQLite + SQLAlchemy 2.0. Modelo `Lead` (entrada + calificación aplanada + asignación + `motor`). Usa `DATABASE_URL` en Railway; sin ella cae a `data/leads.db`. `iniciar_db()` aplica cada versión de campaña demo una sola vez. |
| `datos_semilla.json` | 10 leads ficticios de campaña Meta/Instagram (3 HOT, 3 WARM, 2 COLD, 2 DESCARTAR), sumas consistentes, `motor: "semilla"`. |
| `api.py` | App FastAPI: vistas web (Jinja2: `/`, `/leads`, `/leads/{id}`, `/nuevo`) + API JSON (`/calificar-lead`, `/demo/calificar`, `/api/leads`, `/api/estadisticas`, `/salud`). `/demo` redirige a `/nuevo`. |
| `templates/`, `static/` | UI. `estilos.css` es el sistema de diseño (tokens en `:root`); `app.js` maneja la página de captura. |
| `railway.json` / `Procfile` / `.python-version` | Despliegue en Railway: `uvicorn api:app --host 0.0.0.0 --port $PORT`, healthcheck `/salud`. |
| `probar_ejemplos.py` + `ejemplos/*.json` | Prueba end-to-end del clasificador con Claude (3 leads de la spec). |
| `tests/test_app.py` | Pruebas de humo sin Claude: siembra, vistas, persistencia, filtros y validación. |
| `n8n/workflow-calificacion-leads.json` | Workflow n8n importable (webhook → API → switch por clasificación). |

## Decisiones de diseño (respetarlas al modificar)

1. **El total y la clasificación se recalculan en código** (validador de `CalificacionLead`
   en `clasificador.py`; umbrales ≥80 HOT, ≥55 WARM, ≥30 COLD). Único lugar para cambiarlos.
2. **Structured outputs, no parseo manual**: nunca reemplazar `messages.parse()` por
   `create()` + `json.loads()`.
3. **Dos motores con contratos distintos**: `POST /calificar-lead` (spec, n8n) exige Claude y
   falla con error claro si no hay key; `POST /api/leads` (la web) es resiliente — usa Claude
   si hay key y cae al simulador si no o si la llamada falla, marcando `motor` en la fila.
   No mezclar estos comportamientos.
4. **Todo lead calificado se persiste** con su `motor` (`claude` | `simulador` | `semilla`);
   la UI siempre muestra el motor (transparencia frente al cliente).
5. **Campos del esquema en español, tal como la spec** (incluye `señales_clave` con ñ en el
   JSON de salida; la columna en DB es `senales_clave` por compatibilidad SQL).
6. El SDK lanza `TypeError` (no `AuthenticationError`) cuando no hay ninguna credencial;
   `api.py` maneja ambos por separado. No eliminar el `except TypeError`.
7. **Colores de clasificación = estados semánticos** (HOT rojo, WARM ámbar, COLD azul,
   DESCARTAR gris), siempre acompañados de etiqueta de texto — nunca color solo. Los
   gráficos de magnitud usan un solo matiz (dorado). Tokens en `static/estilos.css`.
8. La base **no se versiona**; lo que se versiona es `datos_semilla.json`. Producción usa
   PostgreSQL vía `DATABASE_URL`; SQLite es solo el fallback local. No hay framework de
   migraciones; `iniciar_db()` agrega las columnas ClickUp a bases existentes del demo.
9. **ClickUp nunca bloquea la captura**: primero se persiste el lead y luego se intenta crear
   la tarea. Todo fallo se registra; solo HOT/WARM se envían. Los secretos y el equipo viven en variables.
10. `VERSION_SEMILLA` identifica la campaña demo. Cambiarla reemplaza todos los leads una
    sola vez al desplegar; reinicios con la misma versión conservan los leads nuevos.

## Estado: qué está HECHO y verificado ✅

- Clasificador con Claude (structured outputs) + simulador de reglas + validador probado.
- PostgreSQL en Railway, SQLite local, siembra automática, CRUD y agregados.
- App web completa: panel con métricas y gráficos, pipeline con filtros, expediente,
  calificación en vivo con animaciones. Tema oscuro oro/carbono, responsive.
- Configuración de Railway (railway.json + Procfile + healthcheck) y PostgreSQL documentado.
- Integración ClickUp para HOT/WARM con trazabilidad visible en el expediente.
- Pruebas automatizadas con `unittest` (9 casos, sin consumo de Claude ni ClickUp real).
- Workflow n8n validado como JSON.

## Estado: qué NO está hecho / pendiente ⏳

1. **Nunca se ha ejecutado una llamada real a Claude** — sin `ANTHROPIC_API_KEY` en la máquina
   de desarrollo. La calidad de calificación del prompt NO está verificada. Primer paso con
   credenciales: `python probar_ejemplos.py`.
2. **Deploy real en Railway no ejecutado** — la config está lista pero nadie ha hecho el deploy.
   Pasos en README → "Desplegar en Railway" (incluye servicio PostgreSQL).
3. **Nodos finales del workflow n8n son placeholders** (falta CRM/notificaciones reales).
4. **Calibración** con 20–30 leads históricos reales: no iniciada.
5. **Sin CI** — las pruebas existen, pero todavía no se ejecutan automáticamente en GitHub.
6. **Sin autenticación** en el panel — cualquiera con la URL ve el demo. Aceptable para demo;
   inaceptable para producción con datos reales.

## Cómo correr

```powershell
pip install -r requirements.txt
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # opcional (sin ella: simulador)
python -m uvicorn api:app --reload       # http://127.0.0.1:8000
```

Si `python` abre la Microsoft Store en otra computadora, instala Python desde python.org,
activa **Add Python to PATH** y usa `py -m pip` / `py -m uvicorn`.

## Convenciones

- Idioma del código, comentarios, docs, UI y mensajes de error: **español**.
- Windows / PowerShell es el entorno de desarrollo del usuario.
- Mantener el formato de entrada/salida exactamente como lo define la spec original.
