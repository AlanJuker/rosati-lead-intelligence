"""API webhook de calificación de leads BANT — Rosati Motors.

Pensada para recibir leads desde el CRM, Meta Lead Ads, n8n, Zapier o Make
y devolver la calificación que dispara la asignación automática al asesor.

Ejecutar:  uvicorn api:app --reload
"""

import anthropic
from fastapi import FastAPI, HTTPException
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


@app.post("/calificar-lead", response_model=CalificacionLead)
def calificar_lead(lead: LeadEntrada) -> CalificacionLead:
    try:
        return clasificar_lead(lead.model_dump())
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY inválida o ausente")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="Límite de tasa de la API de Anthropic; reintentar")
    except anthropic.APIStatusError as e:
        raise HTTPException(status_code=502, detail=f"Error de la API de Anthropic ({e.status_code})")
    except anthropic.APIConnectionError:
        raise HTTPException(status_code=503, detail="Sin conexión con la API de Anthropic")


@app.get("/salud")
def salud() -> dict:
    return {"estado": "ok"}
