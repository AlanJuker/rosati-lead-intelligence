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
| [clickup.py](clickup.py) | Crea y asigna tareas comerciales para leads HOT/WARM, con prioridad y vencimiento según SLA |
| [api.py](api.py) | Aplicación FastAPI: vistas web (Jinja2) + API JSON + persistencia |
| [templates/](templates/), [static/](static/) | Interfaz — tema oscuro de lujo automotriz |
| [n8n/workflow-calificacion-leads.json](n8n/workflow-calificacion-leads.json) | Workflow n8n importable con routing por clasificación |

**Base de datos:** en Railway usa PostgreSQL mediante `DATABASE_URL`. En local, si esa variable no existe, utiliza SQLite en `data/leads.db`. La campaña demo incluye 10 leads ficticios de Meta/Instagram (3 HOT, 3 WARM, 2 COLD y 2 DESCARTAR). La versión de semillas permite reemplazar una campaña una sola vez sin borrar los leads nuevos en reinicios posteriores.

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
   - Variables de ClickUp descritas en la sección siguiente.
3. **PostgreSQL**: en el canvas del proyecto selecciona *New → Database → PostgreSQL*.
4. **Conexión**: en las variables del servicio web agrega una referencia:
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`
   - Si el servicio tiene otro nombre, selecciona su variable `DATABASE_URL` desde *Add Reference* en lugar de escribirla manualmente.
   - No hace falta adjuntar un volumen al servicio web: PostgreSQL conserva los leads.
5. **Dominio**: *Settings → Networking → Generate Domain* para obtener la URL pública.

Con eso, la URL pública sirve el panel en `/` y el webhook para n8n/Zapier en `POST /calificar-lead`.

## Integración con ClickUp

Después de guardar cada lead, la aplicación crea una tarea en ClickUp únicamente para
clasificaciones **HOT** y **WARM**. Un HOT se crea con prioridad urgente y vencimiento en
2 horas; un WARM, con prioridad alta y vencimiento en 24 horas. Un fallo de ClickUp nunca
impide guardar el lead en PostgreSQL y queda registrado en su expediente.

Configura estas variables en **Railway → servicio web → Variables**:

| Variable | Obligatoria | Cómo obtenerla |
|---|---:|---|
| `CLICKUP_API_TOKEN` | Sí | ClickUp → avatar → **Settings → Apps → API Token → Generate**. Empieza con `pk_`. |
| `CLICKUP_LIST_ID` | Sí | Abre la Lista comercial; es el número que aparece en la URL después de `/l/` o `/li/`. |
| `CLICKUP_ASSIGNEES` | Recomendada | Comerciales en formato `id:nombre,id:nombre`. Acepta tantas personas como necesites. |
| `CLICKUP_ASSIGNMENT_MODE` | No | `round_robin` reparte una tarea a una persona; `all` asigna cada tarea a todos. |
| `CLICKUP_STATUS` | No | Nombre exacto del estado de la Lista, por ejemplo `to do`. Si se omite, ClickUp usa el estado inicial. |
| `APP_BASE_URL` | Recomendada | Dominio público del demo, por ejemplo `https://tu-app.up.railway.app`; se incluye en la tarea. |

Para consultar el ID del usuario comercial desde PowerShell:

```powershell
$token = "pk_..."
Invoke-RestMethod "https://api.clickup.com/api/v2/team" -Headers @{ Authorization = $token } |
  ConvertTo-Json -Depth 8
```

Busca el usuario por nombre o correo dentro de `teams → members → user` y copia su `id`.
No guardes el token en Git ni en `.env.example`; debe existir solamente como secreto local
o variable de Railway.

Para Pao y Alan, configura:

```env
CLICKUP_ASSIGNEES=114110475:Pao Barreno,87456941:Alan Guijarro
CLICKUP_ASSIGNMENT_MODE=round_robin
```

Con `round_robin`, cada lead tiene un solo responsable y la carga se distribuye entre los
comerciales. Para agregar otra persona, añade `,ID:Nombre` al final de la misma variable.

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
