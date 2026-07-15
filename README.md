# Sistema de Calificación de Leads BANT — Rosati Motors

Implementación del sistema descrito en [prompt-calificacion-leads-BANT-RosatiMotors (2).md](<prompt-calificacion-leads-BANT-RosatiMotors (2).md>): un servicio que recibe leads de Instagram/Facebook Ads o del formulario web, los envía a Claude con el prompt BANT y devuelve la calificación en el JSON obligatorio (HOT / WARM / COLD / DESCARTAR).

## Estructura

| Archivo | Qué hace |
|---|---|
| [prompt_sistema.md](prompt_sistema.md) | El prompt de sistema BANT (editable sin tocar código) |
| [clasificador.py](clasificador.py) | Lógica central: llama a Claude (`claude-opus-4-8`) con **structured outputs**, que garantizan que la respuesta cumple el esquema — el total y la clasificación se recalculan en código para blindar la aritmética |
| [api.py](api.py) | API HTTP (FastAPI) con el endpoint `POST /calificar-lead` para integrar con CRM, Meta Lead Ads, n8n, Zapier o Make |
| [probar_ejemplos.py](probar_ejemplos.py) | Corre los 3 leads simulados del documento y muestra la calificación |
| [ejemplos/](ejemplos/) | Los 3 leads de prueba (HOT, WARM, DESCARTAR) |
| [n8n/workflow-calificacion-leads.json](n8n/workflow-calificacion-leads.json) | Workflow de n8n importable: webhook → calificación → routing por clasificación |

## Puesta en marcha

```powershell
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Configurar la API key de Anthropic
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# 3. Probar con los leads de ejemplo
python probar_ejemplos.py

# 4. Levantar la API
uvicorn api:app --reload
```

Con la API corriendo, la documentación interactiva queda en `http://127.0.0.1:8000/docs`.

## Ejemplo de llamada al webhook

```powershell
curl -X POST http://127.0.0.1:8000/calificar-lead `
  -H "Content-Type: application/json" `
  -d '@ejemplos/lead_hot.json'
```

Respuesta (formato garantizado por structured outputs):

```json
{
  "lead_id_sugerido": "...",
  "puntajes": { "budget": 25, "authority": 25, "need": 24, "timeline": 23 },
  "puntaje_total": 97,
  "clasificacion": "HOT",
  "showroom_recomendado": "Samborondón",
  "perfil_estimado": "Empresario/inversor con alta probabilidad de compra",
  "señales_clave": ["..."],
  "alertas_red_flags": [],
  "accion_recomendada": "..."
}
```

## Integración con n8n

En [n8n/workflow-calificacion-leads.json](n8n/workflow-calificacion-leads.json) hay un workflow listo para importar (n8n → **Workflows → Import from File**). El flujo es:

```
Webhook (POST /webhook/lead-entrante)
   → HTTP Request a la API BANT (POST http://localhost:8000/calificar-lead)
       → Respond to Webhook (devuelve la calificación al origen)
       → Switch por clasificacion
            ├── 🔴 HOT       → asignar a asesor senior, contacto en <2 horas
            ├── 🟠 WARM      → asignar a asesor, contacto en <24 horas
            ├── 🟡 COLD      → nutrir por email/remarketing, no pasar a ventas aún
            └── ⚪ DESCARTAR → lista de remarketing de marca
```

Después de importar:

1. **Ajusta la URL** del nodo "Calificar lead (API BANT)" si la API no corre en `localhost:8000`. Ojo: si usas **n8n Cloud**, no puede alcanzar tu localhost — despliega la API en un servidor o expón un túnel (ngrok, Cloudflare Tunnel).
2. **Reemplaza los 4 nodos finales** (son placeholders `NoOp`) por las acciones reales: crear tarea en el CRM, notificar por WhatsApp/Slack al asesor, agregar a la audiencia de remarketing, etc.
3. **Conecta la entrada real**: el webhook acepta el JSON del lead directamente, o puedes sustituirlo por el trigger nativo de **Meta Lead Ads** (Facebook Lead Ads Trigger) mapeando los campos del formulario al formato de entrada.

Recuerda inyectar en `datos_adicionales_perfil` la bio/cargo/actividad que marketing extraiga del perfil social — es el campo clave para los leads de Ads, que traen menos datos estructurados.

El mismo endpoint sirve igual para Zapier o Make: es un webhook HTTP estándar que recibe el JSON de entrada y devuelve el JSON de calificación.

## Calibración

Corre 20–30 leads históricos reales contra `clasificar_lead()` y compara la clasificación sugerida vs. la decisión manual del equipo de ventas. Los umbrales (80/55/30) están centralizados en el validador de `clasificador.py` si necesitas ajustarlos.
