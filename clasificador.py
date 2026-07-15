"""Clasificador de leads BANT para Rosati Motors.

Envía el lead a Claude con el prompt de sistema BANT y devuelve la
calificación validada contra el esquema de salida obligatorio.
"""

import json
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, Field, model_validator

MODELO = "claude-opus-4-8"

PROMPT_SISTEMA = (Path(__file__).parent / "prompt_sistema.md").read_text(encoding="utf-8")


class Puntajes(BaseModel):
    budget: int = Field(ge=0, le=25)
    authority: int = Field(ge=0, le=25)
    need: int = Field(ge=0, le=25)
    timeline: int = Field(ge=0, le=25)


class CalificacionLead(BaseModel):
    lead_id_sugerido: str
    puntajes: Puntajes
    puntaje_total: int = Field(ge=0, le=100)
    clasificacion: Literal["HOT", "WARM", "COLD", "DESCARTAR"]
    showroom_recomendado: Literal[
        "Quito - Av. de los Shyris", "Samborondón", "Por confirmar"
    ]
    perfil_estimado: str
    señales_clave: list[str] = Field(min_length=1)
    alertas_red_flags: list[str]
    accion_recomendada: str

    @model_validator(mode="after")
    def _derivar_total_y_clasificacion(self) -> "CalificacionLead":
        # La suma y los umbrales son deterministas: se recalculan en código
        # para que un desliz aritmético del modelo nunca llegue al CRM.
        p = self.puntajes
        self.puntaje_total = p.budget + p.authority + p.need + p.timeline
        if self.puntaje_total >= 80:
            self.clasificacion = "HOT"
        elif self.puntaje_total >= 55:
            self.clasificacion = "WARM"
        elif self.puntaje_total >= 30:
            self.clasificacion = "COLD"
        else:
            self.clasificacion = "DESCARTAR"
        return self


def clasificar_lead(lead: dict, client: anthropic.Anthropic | None = None) -> CalificacionLead:
    """Califica un lead (dict con el formato de entrada del prompt)."""
    client = client or anthropic.Anthropic()
    respuesta = client.messages.parse(
        model=MODELO,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=PROMPT_SISTEMA,
        messages=[{"role": "user", "content": json.dumps(lead, ensure_ascii=False)}],
        output_format=CalificacionLead,
    )
    if respuesta.parsed_output is None:
        raise RuntimeError(
            f"El modelo no devolvió una calificación válida (stop_reason={respuesta.stop_reason})"
        )
    return respuesta.parsed_output
