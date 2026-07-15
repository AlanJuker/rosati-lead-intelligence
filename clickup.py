"""Integración saliente con ClickUp para leads comerciales HOT y WARM."""

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger("rosati.clickup")
API_CLICKUP = "https://api.clickup.com/api/v2"
CLASIFICACIONES_ENVIABLES = {"HOT", "WARM"}


def clickup_configurado() -> bool:
    """Indica si existen credenciales, Lista y al menos un responsable."""
    return bool(
        os.environ.get("CLICKUP_API_TOKEN")
        and os.environ.get("CLICKUP_LIST_ID")
        and (os.environ.get("CLICKUP_ASSIGNEES") or os.environ.get("CLICKUP_ASSIGNEE_ID"))
    )


def _comerciales_configurados() -> list[dict]:
    """Lee `id:nombre,id:nombre`; conserva compatibilidad con el ID único anterior."""
    configuracion = os.environ.get("CLICKUP_ASSIGNEES", "").strip()
    if not configuracion:
        assignee_id = os.environ.get("CLICKUP_ASSIGNEE_ID", "").strip()
        if not assignee_id:
            return []
        configuracion = f"{assignee_id}:Usuario ClickUp"

    comerciales = []
    for item in configuracion.split(","):
        assignee_id, separador, nombre = item.strip().partition(":")
        if not assignee_id.isdigit():
            raise ValueError("Cada comercial de CLICKUP_ASSIGNEES debe tener un ID numérico")
        comerciales.append(
            {
                "id": int(assignee_id),
                "nombre": (
                    nombre.strip()
                    if separador and nombre.strip()
                    else f"Usuario {assignee_id}"
                ),
            }
        )
    return comerciales


def _seleccionar_comerciales(indice_asignacion: int) -> list[dict]:
    comerciales = _comerciales_configurados()
    if not comerciales:
        return []
    modo = os.environ.get("CLICKUP_ASSIGNMENT_MODE", "round_robin").strip().lower()
    if modo == "all":
        return comerciales
    if modo != "round_robin":
        raise ValueError("CLICKUP_ASSIGNMENT_MODE debe ser round_robin o all")
    return [comerciales[(indice_asignacion - 1) % len(comerciales)]]


def _url_expediente(lead_db_id: int) -> str | None:
    base = os.environ.get("APP_BASE_URL", "").strip().rstrip("/")
    if not base:
        dominio = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip().rstrip("/")
        base = f"https://{dominio}" if dominio else ""
    return f"{base}/leads/{lead_db_id}" if base else None


def _descripcion(
    entrada: dict, calificacion: dict, crm: dict, lead_db_id: int
) -> str:
    puntajes = calificacion["puntajes"]
    senales = "\n".join(f"- {senal}" for senal in calificacion["señales_clave"])
    enlace = _url_expediente(lead_db_id)
    contacto = " · ".join(
        valor for valor in (entrada.get("telefono"), entrada.get("email")) if valor
    ) or "Sin teléfono ni email"
    lineas = [
        f"## Lead {calificacion['clasificacion']} · {calificacion['puntaje_total']}/100",
        f"**Contacto:** {contacto}",
        f"**Fuente:** {entrada['fuente']}",
        f"**Ubicación:** {entrada.get('ciudad_o_ubicacion') or 'Por confirmar'}",
        f"**Modelo:** {entrada.get('modelo_interes') or 'Por confirmar'}",
        f"**Showroom:** {calificacion['showroom_recomendado']}",
        "",
        f"**Mensaje:** {entrada['mensaje_o_comentario']}",
        "",
        "### BANT",
        (
            f"Budget {puntajes['budget']}/25 · Authority {puntajes['authority']}/25 · "
            f"Need {puntajes['need']}/25 · Timeline {puntajes['timeline']}/25"
        ),
        "",
        "### Señales clave",
        senales,
        "",
        f"**Acción recomendada:** {calificacion['accion_recomendada']}",
        f"**SLA:** {crm['sla']}",
    ]
    if enlace:
        lineas.extend(("", f"[Abrir expediente completo]({enlace})"))
    return "\n".join(lineas)


def crear_tarea_lead(
    entrada: dict,
    calificacion: dict,
    crm: dict,
    lead_db_id: int,
    client: httpx.Client | None = None,
    indice_asignacion: int | None = None,
) -> dict:
    """Crea una tarea de ClickUp; nunca propaga fallos al flujo del lead."""
    clasificacion = calificacion["clasificacion"]
    if clasificacion not in CLASIFICACIONES_ENVIABLES:
        return {"estado": "omitido", "motivo": "ClickUp recibe únicamente leads HOT y WARM"}

    token = os.environ.get("CLICKUP_API_TOKEN", "").strip()
    list_id = os.environ.get("CLICKUP_LIST_ID", "").strip()
    if not token or not list_id:
        return {"estado": "no_configurado", "motivo": "Faltan CLICKUP_API_TOKEN o CLICKUP_LIST_ID"}
    if not list_id.isdigit():
        return {"estado": "error", "detalle": "CLICKUP_LIST_ID debe contener solo números"}

    ahora = datetime.now(timezone.utc)
    vencimiento = ahora + timedelta(hours=2 if clasificacion == "HOT" else 24)
    payload: dict = {
        "name": (
            f"[{clasificacion}] {entrada['nombre']} · "
            f"{entrada.get('modelo_interes') or 'Modelo por confirmar'}"
        )[:240],
        "markdown_content": _descripcion(entrada, calificacion, crm, lead_db_id),
        "priority": 1 if clasificacion == "HOT" else 2,
        "due_date": int(vencimiento.timestamp() * 1000),
        "due_date_time": True,
        "notify_all": False,
    }
    try:
        comerciales_asignados = _seleccionar_comerciales(indice_asignacion or lead_db_id)
    except ValueError as error:
        return {"estado": "error", "detalle": str(error)}
    if not comerciales_asignados:
        return {"estado": "no_configurado", "motivo": "Falta CLICKUP_ASSIGNEES"}
    payload["assignees"] = [comercial["id"] for comercial in comerciales_asignados]
    status = os.environ.get("CLICKUP_STATUS", "").strip()
    if status:
        payload["status"] = status

    def enviar(cliente: httpx.Client) -> dict:
        try:
            respuesta = cliente.post(
                f"{API_CLICKUP}/list/{list_id}/task",
                headers={"Authorization": token, "Content-Type": "application/json"},
                json=payload,
            )
            respuesta.raise_for_status()
            tarea = respuesta.json()
            return {
                "estado": "creado",
                "task_id": tarea.get("id"),
                "url": tarea.get("url"),
                "prioridad": "urgente" if clasificacion == "HOT" else "alta",
                "asignados": comerciales_asignados,
            }
        except httpx.HTTPStatusError as error:
            detalle = error.response.text[:300] or f"HTTP {error.response.status_code}"
            log.warning("ClickUp rechazó el lead %s: %s", lead_db_id, detalle)
            return {"estado": "error", "detalle": detalle}
        except (httpx.RequestError, ValueError) as error:
            log.warning("ClickUp no disponible para el lead %s: %s", lead_db_id, error)
            return {"estado": "error", "detalle": "No se pudo conectar con ClickUp"}

    if client is not None:
        return enviar(client)
    with httpx.Client(timeout=8.0) as cliente:
        return enviar(cliente)
