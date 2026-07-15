"""API webhook de calificación de leads BANT — Rosati Motors.

Pensada para recibir leads desde el CRM, Meta Lead Ads, n8n, Zapier o Make
y devolver la calificación que dispara la asignación automática al asesor.

Ejecutar:  uvicorn api:app --reload
"""

import re
import unicodedata
from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from clasificador import CalificacionLead, clasificar_lead

app = FastAPI(
    title="Calificación de Leads BANT — Rosati Motors",
    description="Recibe un lead de Instagram/Facebook Ads o formulario web y "
    "devuelve su calificación BANT (HOT / WARM / COLD / DESCARTAR).",
)


class LeadEntrada(BaseModel):
    fuente: str
    fecha: str
    nombre: str
    telefono: str | None = None
    email: str | None = None
    ciudad_o_ubicacion: str | None = None
    modelo_interes: str | None = None
    mensaje_o_comentario: str
    datos_adicionales_perfil: str | None = None


def _texto_normalizado(lead: LeadEntrada) -> str:
    """Une campos relevantes para las reglas transparentes del modo demo."""
    texto = " ".join(str(valor or "") for valor in (
        lead.nombre, lead.ciudad_o_ubicacion, lead.modelo_interes,
        lead.mensaje_o_comentario, lead.datos_adicionales_perfil,
    )).lower()
    return "".join(caracter for caracter in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(caracter) != "Mn")


def _incluye(texto: str, *terminos: str) -> bool:
    return any(termino in texto for termino in terminos)


def _resultado_demo(lead: LeadEntrada) -> dict:
    """Simula una calificación y su destino comercial sin servicios externos."""
    texto = _texto_normalizado(lead)
    fan = _incluye(texto, "algun dia", "mi sueno", "mas fotos", "que carro", "brutal")
    budget = 25 if _incluye(texto, "contado", "cash buyer", "pre-aprobado", "preaprobado") else 22 if _incluye(texto, "gerente", "ceo", "empresario", "inversor", "inmobiliario") else 14 if _incluye(texto, "financiamiento", "financiacion") else (2 if fan else 6)
    authority = 3 if _incluye(texto, "para un amigo", "para mi jefe", "para alguien") else 25 if _incluye(texto, "gerente", "ceo", "empresario", "inversor") else 16 if _incluye(texto, "quiero", "busco", "me interesa", "evaluando") else 5
    need = 25 if _incluye(texto, "test drive", "visita", "cita", "showroom") else 18 if _incluye(texto, "comprar", "renovar", "evaluando", "financiamiento", "disponibilidad") else (2 if fan else 7)
    timeline = 25 if _incluye(texto, "esta semana", "hoy", "manana", "mañana") else 14 if _incluye(texto, "fin de ano", "fin de año", "proximos meses", "próximos meses", "trimestre") else (2 if fan else 6)
    puntajes = {"budget": budget, "authority": authority, "need": need, "timeline": timeline}
    total = sum(puntajes.values())
    clasificacion = "HOT" if total >= 80 else "WARM" if total >= 55 else "COLD" if total >= 30 else "DESCARTAR"
    ubicacion = _texto_normalizado(lead)
    showroom = "Quito - Av. de los Shyris" if "quito" in ubicacion else "Samborondón" if "samborondon" in ubicacion else "Por confirmar"
    nombre_normalizado = "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", lead.nombre.lower())
        if unicodedata.category(caracter) != "Mn"
    )
    slug = re.sub(r"[^a-z0-9]+", "-", nombre_normalizado).strip("-") or "lead"
    calificacion = CalificacionLead(
        lead_id_sugerido=f"DEMO-{slug.upper()}", puntajes=puntajes,
        puntaje_total=total, clasificacion=clasificacion, showroom_recomendado=showroom,
        perfil_estimado="Prospecto con intención de compra" if total >= 55 else "Prospecto en etapa temprana de evaluación",
        señales_clave=[f"{dimension.title()}: {puntaje}/25" for dimension, puntaje in puntajes.items()],
        alertas_red_flags=["Interés principalmente aspiracional o informativo"] if total < 30 else [],
        accion_recomendada="Contactar y agendar una conversación comercial" if total >= 55 else "Incluir en secuencia de nutrición y remarketing",
    )
    destinos = {
        "HOT": ("Valentina Reyes", "Asesora senior", "Contacto inmediato", "Contactar en menos de 2 horas"),
        "WARM": ("Camila Paredes", "Asesora comercial", "Seguimiento prioritario", "Contactar en menos de 24 horas"),
        "COLD": ("Automatización de marketing", "Nurturing", "Nutrición automática", "Enviar contenido y revaluar en 14 días"),
        "DESCARTAR": ("Audiencia de marca", "Remarketing", "Remarketing", "No asignar a ventas"),
    }
    asesor, rol, etapa, sla = destinos[calificacion.clasificacion]
    return {"calificacion": calificacion.model_dump(), "crm": {
        "plataforma": "CRM conectado", "estado": "Lead creado y sincronizado", "etapa": etapa,
        "asesor": asesor, "rol_asesor": rol, "sla": sla,
    }, "modo": "demo"}


@app.post("/calificar-lead", response_model=CalificacionLead)
def calificar_lead(lead: LeadEntrada) -> CalificacionLead:
    try:
        return clasificar_lead(lead.model_dump())
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


@app.get("/salud")
def salud() -> dict:
    return {"estado": "ok"}


@app.post("/demo/calificar")
def calificar_demo(lead: LeadEntrada) -> dict:
    """Simula el flujo completo para presentaciones, sin llamar a servicios externos."""
    return _resultado_demo(lead)


@app.get("/demo", include_in_schema=False)
def demo() -> FileResponse:
    return FileResponse(Path(__file__).parent / "demo.html")
