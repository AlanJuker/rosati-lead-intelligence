"""Simulador de calificación BANT — reglas transparentes, sin servicios externos.

Permite recorrer el flujo completo (calificar → CRM → asignación) en
presentaciones sin ANTHROPIC_API_KEY. Sus reglas son solo de demostración:
no reemplazan a `clasificador.clasificar_lead()`, que evalúa con Claude.
"""

import re
import unicodedata

from clasificador import CalificacionLead

ASIGNACIONES_CRM = {
    "HOT": {
        "asesor": "Valentina Reyes",
        "rol_asesor": "Asesora senior",
        "etapa": "Contacto inmediato",
        "sla": "Contactar en menos de 2 horas",
    },
    "WARM": {
        "asesor": "Camila Paredes",
        "rol_asesor": "Asesora comercial",
        "etapa": "Seguimiento prioritario",
        "sla": "Contactar en menos de 24 horas",
    },
    "COLD": {
        "asesor": "Automatización de marketing",
        "rol_asesor": "Nurturing",
        "etapa": "Nutrición automática",
        "sla": "Enviar contenido y revaluar en 14 días",
    },
    "DESCARTAR": {
        "asesor": "Audiencia de marca",
        "rol_asesor": "Remarketing",
        "etapa": "Remarketing",
        "sla": "No asignar a ventas",
    },
}


def asignacion_crm(clasificacion: str) -> dict:
    """Asesor, etapa y SLA que corresponden a una clasificación."""
    return dict(ASIGNACIONES_CRM[clasificacion])


def _sin_acentos(texto: str) -> str:
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )


def _texto_normalizado(lead: dict) -> str:
    texto = " ".join(
        str(lead.get(campo) or "")
        for campo in (
            "nombre",
            "ciudad_o_ubicacion",
            "modelo_interes",
            "mensaje_o_comentario",
            "datos_adicionales_perfil",
        )
    ).lower()
    return _sin_acentos(texto)


def _incluye(texto: str, *terminos: str) -> bool:
    return any(termino in texto for termino in terminos)


def calificar_simulado(lead: dict) -> CalificacionLead:
    """Califica un lead con reglas heurísticas transparentes (modo demo)."""
    texto = _texto_normalizado(lead)
    fan = _incluye(texto, "algun dia", "mi sueno", "mas fotos", "que carro", "brutal")

    if _incluye(texto, "contado", "cash buyer", "pre-aprobado", "preaprobado"):
        budget = 25
    elif _incluye(texto, "gerente", "ceo", "empresario", "inversor", "inmobiliario"):
        budget = 22
    elif _incluye(texto, "financiamiento", "financiacion"):
        budget = 14
    else:
        budget = 2 if fan else 6

    if _incluye(texto, "para un amigo", "para mi jefe", "para alguien"):
        authority = 3
    elif _incluye(texto, "gerente", "ceo", "empresario", "inversor"):
        authority = 25
    elif _incluye(texto, "quiero", "busco", "me interesa", "evaluando"):
        authority = 16
    else:
        authority = 5

    if _incluye(texto, "test drive", "visita", "cita", "showroom"):
        need = 25
    elif _incluye(texto, "comprar", "renovar", "evaluando", "financiamiento", "disponibilidad"):
        need = 18
    else:
        need = 2 if fan else 7

    if _incluye(texto, "esta semana", "hoy", "manana"):
        timeline = 25
    elif _incluye(texto, "fin de ano", "proximos meses", "trimestre"):
        timeline = 14
    else:
        timeline = 2 if fan else 6

    puntajes = {"budget": budget, "authority": authority, "need": need, "timeline": timeline}
    total = sum(puntajes.values())

    if "quito" in texto:
        showroom = "Quito - Av. de los Shyris"
    elif _incluye(texto, "samborondon", "guayaquil", "duran"):
        showroom = "Samborondón"
    else:
        showroom = "Por confirmar"

    slug = re.sub(r"[^a-z0-9]+", "-", _sin_acentos(lead["nombre"].lower())).strip("-") or "lead"

    return CalificacionLead(
        lead_id_sugerido=f"DEMO-{slug.upper()}",
        puntajes=puntajes,
        puntaje_total=total,  # el validador lo recalcula igual
        clasificacion="DESCARTAR",  # el validador la recalcula desde los puntajes
        showroom_recomendado=showroom,
        perfil_estimado=(
            "Prospecto con intención de compra"
            if total >= 55
            else "Prospecto en etapa temprana de evaluación"
        ),
        señales_clave=[
            f"{dimension.title()}: {puntaje}/25" for dimension, puntaje in puntajes.items()
        ],
        alertas_red_flags=(
            ["Interés principalmente aspiracional o informativo"] if total < 30 else []
        ),
        accion_recomendada=(
            "Contactar y agendar una conversación comercial"
            if total >= 55
            else "Incluir en secuencia de nutrición y remarketing"
        ),
    )
