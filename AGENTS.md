# Contexto del proyecto — Sistema de Calificación de Leads BANT (Rosati Motors)

Guía para agentes de código (Codex, Claude Code, etc.) que trabajen en este repo.
Última actualización: 2026-07-15.

## Qué es este proyecto

Implementación del sistema descrito en `prompt-calificacion-leads-BANT-RosatiMotors (2).md`
(el documento de especificación original — **no editarlo**, es la fuente de requisitos).
Rosati Motors es un concesionario de ultra-lujo en Ecuador (Lamborghini, Maserati, McLaren);
el sistema recibe leads de Instagram/Facebook Ads o formulario web, los envía a Claude con
un prompt BANT y devuelve una calificación JSON (HOT / WARM / COLD / DESCARTAR) que dispara
la asignación automática al equipo de ventas vía n8n.

## Arquitectura y archivos

| Archivo | Rol |
|---|---|
| `prompt_sistema.md` | Prompt de sistema BANT que se envía a Claude. Extraído casi verbatim de la spec. Editable por negocio sin tocar código. |
| `clasificador.py` | Núcleo. `clasificar_lead(dict) -> CalificacionLead`. Usa el SDK oficial `anthropic` con `client.messages.parse()` + `output_format=<modelo Pydantic>` (structured outputs: la API garantiza que la respuesta cumple el esquema). Modelo: `claude-opus-4-8`, thinking adaptativo. |
| `api.py` | Webhook FastAPI. `POST /calificar-lead` (producción con Claude), `POST /demo/calificar` (simulación sin IA externa), `GET /salud` y `GET /demo`. |
| `demo.html` | Interfaz de presentación para cliente: formulario → BANT → CRM simulado → asesor/SLA asignado. La sirve `GET /demo`. |
| `probar_ejemplos.py` | Corre los 3 leads de `ejemplos/` contra el clasificador e imprime resultados. Requiere `ANTHROPIC_API_KEY`. |
| `ejemplos/*.json` | Los 3 leads simulados de la spec: `lead_hot.json`, `lead_warm.json`, `lead_descartar.json`. Sus nombres indican la clasificación esperada. |
| `n8n/workflow-calificacion-leads.json` | Workflow n8n importable: Webhook → HTTP Request a la API → Respond to Webhook + Switch por `clasificacion` con 4 salidas (los nodos finales son placeholders NoOp a reemplazar por acciones reales). |

## Decisiones de diseño (respetarlas al modificar)

1. **El total y la clasificación se recalculan en código**, no se confía en la aritmética
   del modelo: el `model_validator` de `CalificacionLead` en `clasificador.py` suma los 4
   puntajes y aplica los umbrales (>=80 HOT, >=55 WARM, >=30 COLD, resto DESCARTAR).
   Si se cambian los umbrales, ese validador es el único lugar.
2. **Structured outputs, no parseo manual**: nunca reemplazar `messages.parse()` por
   `messages.create()` + `json.loads()` del texto.
3. **El prompt vive en `prompt_sistema.md`**, no como string en Python, para que
   marketing/ventas pueda ajustarlo.
4. **Campos del esquema en español, tal como los define la spec** (incluye `señales_clave`
   con ñ — identificador Python válido; no "arreglarlo" a ASCII).
5. El SDK lanza `TypeError` (no `AuthenticationError`) cuando no hay ninguna credencial
   configurada; `api.py` maneja ambos casos por separado. No eliminar el `except TypeError`.

## Estado: qué está HECHO y verificado ✅

- Código completo de clasificador, API, ejemplos, script de prueba y workflow n8n.
- Dependencias instaladas (Python 3.13, `anthropic` 0.116.0, FastAPI). Imports OK.
- Validador probado con datos deliberadamente incorrectos: recalcula total/clasificación bien.
- Servidor levantado y probado en vivo: `GET /salud` → 200; `GET /docs` → 200;
  body inválido → 422 con detalle de campos; lead válido sin API key → 500 con mensaje claro.
- Workflow n8n validado como JSON bien formado (8 nodos).
- Demo para cliente implementada y probada: `GET /demo` y `POST /demo/calificar`.
  No requiere `ANTHROPIC_API_KEY`; los escenarios HOT/WARM/DESCARTAR muestran puntajes,
  sincronización de CRM simulada, asesor y SLA. Sus reglas son solo de presentación:
  no reemplazan `clasificar_lead()` ni la evaluación real con Claude.

## Estado: qué NO está hecho / pendiente ⏳

1. **Nunca se ha ejecutado una llamada real a Claude** — no hay `ANTHROPIC_API_KEY` en la
   máquina de desarrollo. Por tanto la calidad de la calificación (que los 3 ejemplos
   salgan HOT/WARM/DESCARTAR como se espera) NO está verificada. Primer paso para
   cualquier agente con credenciales: `python probar_ejemplos.py`.
2. **Nodos finales del workflow n8n son placeholders** — falta conectar CRM/notificaciones
   reales, y decidir si la entrada será el webhook genérico o el trigger de Meta Lead Ads.
3. **Calibración** — la spec recomienda correr 20–30 leads históricos reales y comparar
   contra el criterio manual del equipo de ventas antes de producción. No iniciado.
4. **Sin tests automatizados** (pytest) ni CI. El único harness es `probar_ejemplos.py`,
   que requiere API key y gasta tokens.
5. **Sin despliegue** — la API solo ha corrido en localhost. n8n Cloud no alcanza
   localhost; para producción hará falta desplegar la API o un túnel.

## Cómo correr

```powershell
pip install -r requirements.txt
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # requerida para clasificar
python probar_ejemplos.py                # prueba end-to-end con los 3 ejemplos
python -m uvicorn api:app --reload       # API en http://127.0.0.1:8000/docs
```

En la máquina donde se desarrolló el demo, el ejecutable disponible fue
`C:\Users\paola\AppData\Local\Python\bin\python.exe` (Python 3.14). Si `python`
o `py` abren la Microsoft Store en otra computadora, instala Python desde python.org,
activa **Add Python to PATH** y usa `py -m pip` / `py -m uvicorn`.

Para presentar sin credenciales de Anthropic:

```powershell
python -m uvicorn api:app --host 127.0.0.1 --port 8000
# Abrir http://127.0.0.1:8000/demo
```

Prueba rápida del webhook:

```powershell
curl.exe -X POST http://127.0.0.1:8000/calificar-lead -H "Content-Type: application/json" --data-binary "@ejemplos/lead_hot.json"
```

## Convenciones

- Idioma del código, comentarios, docs y mensajes de error: **español**.
- Windows / PowerShell es el entorno de desarrollo del usuario.
- Mantener el formato de entrada/salida exactamente como lo define la spec original.
