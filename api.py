"""Rosati Motors · Lead Intelligence — aplicación web + API BANT.

Superficie:
  Web (HTML): /            panel con métricas y gráficos
              /leads       pipeline con filtros
              /leads/{id}  expediente de un lead
              /nuevo       captura y calificación en vivo
  JSON:       POST /calificar-lead   contrato de la spec (Claude, para n8n/CRM)
              POST /demo/calificar   simulador sin API key (compatibilidad demo)
              POST /api/leads        califica con el mejor motor disponible y persiste
              GET  /api/leads        lista de leads
              GET  /api/estadisticas agregados del panel
              GET  /salud            healthcheck (usado por Railway)

Ejecutar:  uvicorn api:app --reload
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

import db
from clickup import clickup_configurado, crear_tarea_lead
from clasificador import CalificacionLead, clasificar_lead
from simulador import asignacion_crm, calificar_simulado

log = logging.getLogger("rosati")
_RAIZ = Path(__file__).parent

CLASIFICACIONES = ["HOT", "WARM", "COLD", "DESCARTAR"]
FUENTES = ["Instagram Ads", "Facebook Ads", "Formulario Web"]
DIMENSIONES_BANT = ["budget", "authority", "need", "timeline"]


def _sincronizar_pendientes_clickup() -> dict:
    """Crea al arrancar las tareas faltantes y evita duplicados por task_id."""
    if not clickup_configurado():
        log.info("ClickUp no está configurado; se omite la sincronización inicial")
        return {"creados": 0, "errores": 0, "pendientes": 0}

    pendientes = db.listar_pendientes_clickup()
    creados = errores = 0
    for lead in pendientes:
        entrada = {
            "fuente": lead.fuente,
            "fecha": lead.fecha,
            "nombre": lead.nombre,
            "telefono": lead.telefono,
            "email": lead.email,
            "ciudad_o_ubicacion": lead.ciudad_o_ubicacion,
            "modelo_interes": lead.modelo_interes,
            "mensaje_o_comentario": lead.mensaje_o_comentario,
            "datos_adicionales_perfil": lead.datos_adicionales_perfil,
        }
        calificacion = {
            "clasificacion": lead.clasificacion,
            "puntaje_total": lead.puntaje_total,
            "puntajes": lead.puntajes,
            "showroom_recomendado": lead.showroom_recomendado,
            "señales_clave": lead.senales_clave,
            "accion_recomendada": lead.accion_recomendada,
        }
        crm = {"sla": lead.sla}
        resultado = crear_tarea_lead(
            entrada,
            calificacion,
            crm,
            lead.id,
            indice_asignacion=(
                db.numero_asignacion_semilla(lead.id)
                if lead.motor == "semilla"
                else db.numero_asignacion_comercial(lead.id)
            ),
        )
        db.actualizar_clickup(lead.id, resultado)
        if resultado["estado"] == "creado":
            creados += 1
        else:
            errores += 1

    if pendientes:
        log.info("Sincronización ClickUp: %s creados, %s errores", creados, errores)
    return {"creados": creados, "errores": errores, "pendientes": len(pendientes)}


@asynccontextmanager
async def _ciclo_de_vida(app: FastAPI):
    db.iniciar_db()
    _sincronizar_pendientes_clickup()
    yield


app = FastAPI(
    title="Rosati Motors · Lead Intelligence",
    description="Califica leads con metodología BANT (Claude) y los enruta al "
    "equipo comercial. Panel web en `/`, contrato JSON de la spec en `/calificar-lead`.",
    lifespan=_ciclo_de_vida,
)
app.mount("/static", StaticFiles(directory=_RAIZ / "static"), name="static")
plantillas = Jinja2Templates(directory=_RAIZ / "templates")


class LeadEntrada(BaseModel):
    fuente: str = Field(min_length=2, max_length=50)
    fecha: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")
    nombre: str = Field(min_length=2, max_length=200)
    telefono: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=200)
    ciudad_o_ubicacion: str | None = Field(default=None, max_length=200)
    modelo_interes: str | None = Field(default=None, max_length=200)
    mensaje_o_comentario: str = Field(min_length=3, max_length=5000)
    datos_adicionales_perfil: str | None = Field(default=None, max_length=5000)

    @field_validator("fecha")
    @classmethod
    def _fecha_real(cls, valor: str) -> str:
        try:
            date.fromisoformat(valor)
        except ValueError as error:
            raise ValueError("la fecha debe ser válida y usar el formato YYYY-MM-DD") from error
        return valor

    @field_validator(
        "fuente", "nombre", "telefono", "email", "ciudad_o_ubicacion",
        "modelo_interes", "mensaje_o_comentario", "datos_adicionales_perfil",
        mode="before",
    )
    @classmethod
    def _limpiar_texto(cls, valor: object) -> object:
        if valor is None:
            return None
        if isinstance(valor, str):
            limpio = valor.strip()
            return limpio or None
        return valor


def motor_claude_disponible() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _calificar_resiliente(entrada: dict) -> tuple[CalificacionLead, str]:
    """Claude si hay credenciales; si no (o si la llamada falla), simulador.

    Pensado para la experiencia web del demo: nunca deja al presentador
    frente a un error. El contrato estricto con Claude vive en /calificar-lead.
    """
    if motor_claude_disponible():
        try:
            return clasificar_lead(entrada), "claude"
        except (TypeError, RuntimeError, anthropic.APIConnectionError, anthropic.APIError) as e:
            log.warning("Claude no disponible (%s); se usa el simulador", e)
    return calificar_simulado(entrada), "simulador"


def _persistir_y_enrutar(
    entrada: dict, calificacion: CalificacionLead, motor: str
) -> tuple[db.Lead, dict, dict]:
    """Guarda primero el lead y luego intenta crear su tarea comercial."""
    crm = asignacion_crm(calificacion.clasificacion)
    calificacion_dict = calificacion.model_dump()
    fila = db.guardar_lead(entrada, calificacion_dict, crm, motor)
    try:
        resultado_clickup = crear_tarea_lead(
            entrada,
            calificacion_dict,
            crm,
            fila.id,
            indice_asignacion=db.numero_asignacion_comercial(fila.id),
        )
        db.actualizar_clickup(fila.id, resultado_clickup)
        asignados = resultado_clickup.get("asignados", [])
        if resultado_clickup["estado"] == "creado" and asignados:
            nombres = ", ".join(comercial["nombre"] for comercial in asignados)
            crm = {
                **crm,
                "asesor": nombres,
                "rol_asesor": (
                    "Asesor/a comercial · ClickUp"
                    if len(asignados) == 1
                    else "Equipo comercial · ClickUp"
                ),
            }
    except Exception as error:
        log.exception("No se pudo registrar la integración ClickUp del lead %s", fila.id)
        resultado_clickup = {"estado": "error", "detalle": str(error)}
    return fila, crm, resultado_clickup


# ─────────────────────────── API JSON ───────────────────────────


@app.post("/calificar-lead", response_model=CalificacionLead)
def calificar_lead_spec(lead: LeadEntrada) -> CalificacionLead:
    """Contrato de la spec: califica SIEMPRE con Claude y persiste el resultado."""
    try:
        calificacion = clasificar_lead(lead.model_dump())
    except TypeError:
        # El SDK lanza TypeError cuando no hay ninguna credencial configurada
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada en el servidor")
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY inválida")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="Límite de tasa de la API de Anthropic; reintentar")
    except anthropic.APIStatusError as e:
        raise HTTPException(status_code=502, detail=f"Error de la API de Anthropic ({e.status_code})")
    except anthropic.APIConnectionError:
        raise HTTPException(status_code=503, detail="Sin conexión con la API de Anthropic")
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error))
    _persistir_y_enrutar(lead.model_dump(), calificacion, "claude")
    return calificacion


@app.post("/demo/calificar")
def calificar_demo(lead: LeadEntrada) -> dict:
    """Simulador sin servicios externos (compatibilidad con la demo original)."""
    calificacion = calificar_simulado(lead.model_dump())
    fila, crm, resultado_clickup = _persistir_y_enrutar(
        lead.model_dump(), calificacion, "simulador"
    )
    return {
        "calificacion": calificacion.model_dump(),
        "crm": {"plataforma": "Gestión comercial", "estado": "Lead creado", **crm},
        "clickup": resultado_clickup,
        "modo": "demo",
        "lead_db_id": fila.id,
    }


@app.post("/api/leads")
def crear_lead(lead: LeadEntrada) -> dict:
    """Califica con el mejor motor disponible, persiste y devuelve todo el flujo."""
    calificacion, motor = _calificar_resiliente(lead.model_dump())
    fila, crm, resultado_clickup = _persistir_y_enrutar(
        lead.model_dump(), calificacion, motor
    )
    return {
        "id": fila.id,
        "motor": motor,
        "calificacion": calificacion.model_dump(),
        "crm": {"plataforma": "Gestión comercial", "estado": "Lead creado", **crm},
        "clickup": resultado_clickup,
    }


@app.get("/api/leads")
def listar_leads_json(
    clasificacion: str | None = None, fuente: str | None = None, q: str | None = None
) -> list[dict]:
    return [
        {
            "id": lead.id,
            "fecha": lead.fecha,
            "nombre": lead.nombre,
            "fuente": lead.fuente,
            "modelo_interes": lead.modelo_interes,
            "puntaje_total": lead.puntaje_total,
            "clasificacion": lead.clasificacion,
            "showroom_recomendado": lead.showroom_recomendado,
            "asesor": lead.asesor,
            "motor": lead.motor,
            "clickup_estado": lead.clickup_estado,
            "clickup_task_url": lead.clickup_task_url,
        }
        for lead in db.listar_leads(clasificacion, fuente, q)
    ]


@app.get("/api/estadisticas")
def estadisticas_json() -> dict:
    return db.estadisticas()


@app.get("/salud")
def salud() -> dict:
    return {
        "estado": "ok",
        "leads": db.estadisticas()["total"],
        "motor_claude": motor_claude_disponible(),
        "base_datos": db.TIPO_BD,
        "clickup_configurado": clickup_configurado(),
    }


# ─────────────────────────── Vistas web ───────────────────────────


def _serie_diaria(por_dia: dict, dias: int = 14) -> list[dict]:
    """Serie de conteos por día para el gráfico del panel (últimos N días con datos)."""
    fechas_validas = []
    for texto in por_dia:
        try:
            fechas_validas.append(date.fromisoformat(texto))
        except ValueError:
            continue
    fin = max(fechas_validas) if fechas_validas else date.today()
    serie = []
    maximo = 1
    for i in range(dias - 1, -1, -1):
        dia = fin - timedelta(days=i)
        valor = por_dia.get(dia.isoformat(), 0)
        maximo = max(maximo, valor)
        serie.append({"fecha": dia.isoformat(), "etiqueta": f"{dia.day:02d}", "valor": valor})
    for punto in serie:
        punto["pct"] = round(100 * punto["valor"] / maximo)
    return serie


def _contexto_base() -> dict:
    return {"motor_claude": motor_claude_disponible(), "clasificaciones": CLASIFICACIONES}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def panel(request: Request):
    stats = db.estadisticas()
    total = stats["total"] or 1
    distribucion = [
        {
            "nombre": c,
            "valor": stats["por_clasificacion"][c],
            "pct": round(100 * stats["por_clasificacion"][c] / total),
        }
        for c in CLASIFICACIONES
    ]
    bant = [
        {"nombre": d, "valor": stats["promedios_bant"][d],
         "pct": round(100 * stats["promedios_bant"][d] / 25)}
        for d in DIMENSIONES_BANT
    ]
    return plantillas.TemplateResponse(
        request,
        "panel.html",
        {
            **_contexto_base(),
            "activo": "panel",
            "stats": stats,
            "distribucion": distribucion,
            "bant": bant,
            "serie": _serie_diaria(stats["por_dia"]),
            "recientes": db.listar_leads(limite=6),
        },
    )


@app.get("/leads", response_class=HTMLResponse, include_in_schema=False)
def vista_leads(
    request: Request,
    clasificacion: str | None = None,
    fuente: str | None = None,
    q: str | None = None,
):
    leads = db.listar_leads(clasificacion or None, fuente or None, q or None)
    return plantillas.TemplateResponse(
        request,
        "leads.html",
        {
            **_contexto_base(),
            "activo": "leads",
            "leads": leads,
            "fuentes": FUENTES,
            "filtro_clasificacion": clasificacion or "",
            "filtro_fuente": fuente or "",
            "filtro_q": q or "",
        },
    )


@app.get("/leads/{lead_id}", response_class=HTMLResponse, include_in_schema=False)
def vista_lead(request: Request, lead_id: int):
    lead = db.obtener_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead no encontrado")
    return plantillas.TemplateResponse(
        request,
        "lead_detalle.html",
        {**_contexto_base(), "activo": "leads", "lead": lead},
    )


@app.get("/nuevo", response_class=HTMLResponse, include_in_schema=False)
def vista_nuevo(request: Request):
    return plantillas.TemplateResponse(
        request,
        "nuevo.html",
        {**_contexto_base(), "activo": "nuevo", "hoy": date.today().isoformat()},
    )


@app.get("/demo", include_in_schema=False)
def demo_redireccion() -> RedirectResponse:
    return RedirectResponse("/nuevo", status_code=307)
