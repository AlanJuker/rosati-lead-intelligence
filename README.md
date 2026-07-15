# Rosati Motors · Lead Intelligence — Calificación de Leads BANT

Demo profesional del sistema descrito en [prompt-calificacion-leads-BANT-RosatiMotors (2).md](<prompt-calificacion-leads-BANT-RosatiMotors (2).md>): una aplicación web que recibe leads de Instagram/Facebook Ads o formulario web, los califica con metodología BANT usando Claude, los guarda en una base de datos y los enruta al asesor correcto — con panel de métricas, pipeline filtrable y calificación en vivo.

**Lista para desplegar en Railway** (ver sección más abajo).

## Qué incluye

| Ruta | Qué es |
|---|---|
| `/` | **Panel comercial**: métricas, leads por día, distribución por clasificación, promedios BANT y últimos ingresos |
| `/leads` | **Pipeline** completo con filtros por clasificación, fuente y búsqueda de texto |
| `/leads/{id}` | **Expediente** del lead: puntajes, mensaje, señales, red flags y asignación CRM |
| `/nuevo` | **Calificación en vivo**: formulario con escenarios de ejemplo que recorre el flujo Captura → BANT → CRM → Asignación |
| `/docs` | Documentación interactiva de la API (OpenAPI) |
| `POST /calificar-lead` | Contrato JSON de la spec — **siempre con Claude** (para n8n/Zapier/CRM) |
| `POST /api/leads` | Califica con el mejor motor disponible (Claude si hay API key, simulador si no) y persiste |
| `GET /salud` | Healthcheck (lo usa Railway) |

## Arquitectura

| Archivo | Rol |
|---|---|
| [prompt_sistema.md](prompt_sistema.md) | Prompt de sistema BANT que se envía a Claude (editable sin tocar código) |
| [clasificador.py](clasificador.py) | Llama a Claude (`claude-opus-4-8`) con **structured outputs**; el total y la clasificación se recalculan en código |
| [simulador.py](simulador.py) | Calificación por reglas transparentes — permite demo completa **sin** API key |
| [db.py](db.py) | PostgreSQL en Railway y SQLite como fallback local (SQLAlchemy). Se crea y siembra automáticamente |
| [api.py](api.py) | Aplicación FastAPI: vistas web (Jinja2) + API JSON + persistencia |
| [templates/](templates/), [static/](static/) | Interfaz — tema oscuro de lujo automotriz |
| [n8n/workflow-calificacion-leads.json](n8n/workflow-calificacion-leads.json) | Workflow n8n importable con routing por clasificación |

**Base de datos:** en Railway usa PostgreSQL mediante `DATABASE_URL`. En local, si esa variable no existe, utiliza SQLite en `data/leads.db`. En ambos casos, una base vacía se siembra automáticamente con 18 leads históricos realistas de [datos_semilla.json](datos_semilla.json), por lo que el demo luce poblado desde el primer despliegue.

**Motores de calificación:** con `ANTHROPIC_API_KEY` configurada, la calificación la hace **Claude** con el prompt BANT completo. Sin key, la experiencia web usa un **simulador de reglas** (marcado como tal en la interfaz) para que el demo nunca se caiga frente a un cliente. El endpoint `POST /calificar-lead` de la spec siempre exige Claude.

## Correr en local

```powershell
pip install -r requirements.txt
$env:DATABASE_URL = "postgresql://usuario:clave@localhost:5432/rosati_motors"  # opcional
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # opcional: sin ella, el demo usa el simulador
python -m uvicorn api:app --reload       # abrir http://127.0.0.1:8000
```

Prueba end-to-end del clasificador con Claude (requiere API key): `python probar_ejemplos.py`.

Pruebas de humo del demo (no consumen Claude):

```powershell
python -m unittest discover -s tests -v
```

## Desplegar en Railway

1. **Crear el proyecto**: en [railway.com](https://railway.com) → *New Project* → *Deploy from GitHub repo* → seleccionar este repo. Railway detecta Python y usa el `startCommand` de [railway.json](railway.json) (healthcheck en `/salud` incluido).
2. **Variables** (pestaña *Variables* del servicio):
   - `ANTHROPIC_API_KEY` = `sk-ant-...` — para que la calificación sea con Claude. Sin ella el demo funciona igual con el simulador.
3. **PostgreSQL**: en el canvas del proyecto selecciona *New → Database → PostgreSQL*.
4. **Conexión**: en las variables del servicio web agrega una referencia:
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`
   - Si el servicio tiene otro nombre, selecciona su variable `DATABASE_URL` desde *Add Reference* en lugar de escribirla manualmente.
   - No hace falta adjuntar un volumen al servicio web: PostgreSQL conserva los leads.
5. **Dominio**: *Settings → Networking → Generate Domain* para obtener la URL pública.

Con eso, la URL pública sirve el panel en `/` y el webhook para n8n/Zapier en `POST /calificar-lead`.

## Integración con n8n

En [n8n/workflow-calificacion-leads.json](n8n/workflow-calificacion-leads.json) hay un workflow listo para importar (n8n → **Workflows → Import from File**):

```
Webhook (POST /webhook/lead-entrante)
   → HTTP Request a la API BANT (POST {URL}/calificar-lead)
       → Respond to Webhook (devuelve la calificación al origen)
       → Switch por clasificacion
            ├── 🔴 HOT       → asignar a asesor senior, contacto en <2 horas
            ├── 🟠 WARM      → asignar a asesor, contacto en <24 horas
            ├── 🟡 COLD      → nutrir por email/remarketing
            └── ⚪ DESCARTAR → lista de remarketing de marca
```

Después de importar: apunta el nodo "Calificar lead (API BANT)" a tu dominio de Railway (`https://<tu-app>.up.railway.app/calificar-lead`), reemplaza los 4 nodos finales (placeholders) por tus acciones reales (CRM, WhatsApp, Slack…) y, si quieres, sustituye el webhook por el trigger nativo de **Meta Lead Ads**. El mismo endpoint sirve para Zapier o Make.

## Calibración

Corre 20–30 leads históricos reales contra `POST /calificar-lead` y compara la clasificación sugerida vs. la decisión manual del equipo de ventas. Los umbrales (80/55/30) están centralizados en el validador de [clasificador.py](clasificador.py).
