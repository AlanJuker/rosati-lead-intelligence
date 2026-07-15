"""Capa de datos del sistema de leads — PostgreSQL/SQLite + SQLAlchemy.

En Railway usa PostgreSQL mediante DATABASE_URL. En desarrollo, si esa variable
no existe, cae automáticamente a SQLite en ./data/leads.db. Si la tabla está
vacía al arrancar, carga datos_semilla.json para que el demo luzca poblado.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, DateTime, Integer, String, Text, create_engine, event, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

_RAIZ = Path(__file__).parent
RUTA_SQLITE = _RAIZ / "data" / "leads.db"


def normalizar_url_database(url: str) -> str:
    """Fuerza el driver psycopg 3 para las URLs que entrega Railway."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


_url_entorno = os.environ.get("DATABASE_URL")
if _url_entorno:
    URL_DATABASE = normalizar_url_database(_url_entorno)
    TIPO_BD = "postgresql"
else:
    RUTA_SQLITE.parent.mkdir(parents=True, exist_ok=True)
    URL_DATABASE = f"sqlite:///{RUTA_SQLITE}"
    TIPO_BD = "sqlite"

_opciones_engine = {"pool_pre_ping": True}
if TIPO_BD == "sqlite":
    _opciones_engine["connect_args"] = {"check_same_thread": False, "timeout": 30}

engine = create_engine(URL_DATABASE, **_opciones_engine)


def _configurar_sqlite(conexion, _registro) -> None:
    """Reduce bloqueos y protege escrituras del fallback SQLite local."""
    cursor = conexion.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


if TIPO_BD == "sqlite":
    event.listen(engine, "connect", _configurar_sqlite)


class Base(DeclarativeBase):
    pass


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Entrada (formato de la spec)
    fuente: Mapped[str] = mapped_column(String(50))
    fecha: Mapped[str] = mapped_column(String(10))
    nombre: Mapped[str] = mapped_column(String(200))
    telefono: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ciudad_o_ubicacion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    modelo_interes: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mensaje_o_comentario: Mapped[str] = mapped_column(Text)
    datos_adicionales_perfil: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Calificación BANT (formato de salida de la spec)
    lead_id_sugerido: Mapped[str] = mapped_column(String(100))
    budget: Mapped[int] = mapped_column(Integer)
    authority: Mapped[int] = mapped_column(Integer)
    need: Mapped[int] = mapped_column(Integer)
    timeline: Mapped[int] = mapped_column(Integer)
    puntaje_total: Mapped[int] = mapped_column(Integer)
    clasificacion: Mapped[str] = mapped_column(String(12), index=True)
    showroom_recomendado: Mapped[str] = mapped_column(String(60))
    perfil_estimado: Mapped[str] = mapped_column(Text)
    senales_clave: Mapped[list] = mapped_column(JSON, default=list)
    alertas_red_flags: Mapped[list] = mapped_column(JSON, default=list)
    accion_recomendada: Mapped[str] = mapped_column(Text)

    # Asignación comercial + trazabilidad
    asesor: Mapped[str] = mapped_column(String(100))
    rol_asesor: Mapped[str] = mapped_column(String(100))
    etapa: Mapped[str] = mapped_column(String(100))
    sla: Mapped[str] = mapped_column(String(120))
    motor: Mapped[str] = mapped_column(String(20))  # "claude" | "simulador" | "semilla"

    @property
    def puntajes(self) -> dict:
        return {
            "budget": self.budget,
            "authority": self.authority,
            "need": self.need,
            "timeline": self.timeline,
        }


def iniciar_db() -> None:
    """Crea las tablas y siembra datos de demostración si la base está vacía."""
    Base.metadata.create_all(engine)
    with Session(engine) as sesion:
        if sesion.scalar(select(func.count(Lead.id))):
            return
        ruta_semilla = _RAIZ / "datos_semilla.json"
        if not ruta_semilla.exists():
            return
        for registro in json.loads(ruta_semilla.read_text(encoding="utf-8")):
            registro["creado_en"] = datetime.fromisoformat(registro["creado_en"])
            sesion.add(Lead(**registro))
        sesion.commit()


def guardar_lead(entrada: dict, calificacion: dict, crm: dict, motor: str) -> Lead:
    """Persiste un lead calificado y devuelve la fila creada."""
    with Session(engine) as sesion:
        lead = Lead(
            fuente=entrada["fuente"],
            fecha=entrada["fecha"],
            nombre=entrada["nombre"],
            telefono=entrada.get("telefono"),
            email=entrada.get("email"),
            ciudad_o_ubicacion=entrada.get("ciudad_o_ubicacion"),
            modelo_interes=entrada.get("modelo_interes"),
            mensaje_o_comentario=entrada["mensaje_o_comentario"],
            datos_adicionales_perfil=entrada.get("datos_adicionales_perfil"),
            lead_id_sugerido=calificacion["lead_id_sugerido"],
            budget=calificacion["puntajes"]["budget"],
            authority=calificacion["puntajes"]["authority"],
            need=calificacion["puntajes"]["need"],
            timeline=calificacion["puntajes"]["timeline"],
            puntaje_total=calificacion["puntaje_total"],
            clasificacion=calificacion["clasificacion"],
            showroom_recomendado=calificacion["showroom_recomendado"],
            perfil_estimado=calificacion["perfil_estimado"],
            senales_clave=calificacion["señales_clave"],
            alertas_red_flags=calificacion["alertas_red_flags"],
            accion_recomendada=calificacion["accion_recomendada"],
            asesor=crm["asesor"],
            rol_asesor=crm["rol_asesor"],
            etapa=crm["etapa"],
            sla=crm["sla"],
            motor=motor,
        )
        sesion.add(lead)
        sesion.commit()
        sesion.refresh(lead)
        sesion.expunge(lead)
        return lead


def obtener_lead(lead_id: int) -> Lead | None:
    with Session(engine) as sesion:
        lead = sesion.get(Lead, lead_id)
        if lead:
            sesion.expunge(lead)
        return lead


def listar_leads(
    clasificacion: str | None = None,
    fuente: str | None = None,
    buscar: str | None = None,
    limite: int = 200,
) -> list[Lead]:
    consulta = select(Lead).order_by(Lead.fecha.desc(), Lead.id.desc()).limit(limite)
    if clasificacion:
        consulta = consulta.where(Lead.clasificacion == clasificacion)
    if fuente:
        consulta = consulta.where(Lead.fuente == fuente)
    if buscar:
        patron = f"%{buscar}%"
        consulta = consulta.where(
            Lead.nombre.ilike(patron)
            | Lead.modelo_interes.ilike(patron)
            | Lead.mensaje_o_comentario.ilike(patron)
        )
    with Session(engine) as sesion:
        leads = list(sesion.scalars(consulta))
        for lead in leads:
            sesion.expunge(lead)
        return leads


def estadisticas() -> dict:
    """Agregados para el panel: conteos, promedios y serie temporal."""
    with Session(engine) as sesion:
        total = sesion.scalar(select(func.count(Lead.id))) or 0
        por_clasificacion = {c: 0 for c in ("HOT", "WARM", "COLD", "DESCARTAR")}
        for clasificacion, cuenta in sesion.execute(
            select(Lead.clasificacion, func.count(Lead.id)).group_by(Lead.clasificacion)
        ):
            por_clasificacion[clasificacion] = cuenta

        promedio_total = sesion.scalar(select(func.avg(Lead.puntaje_total))) or 0
        promedios_bant = {
            "budget": sesion.scalar(select(func.avg(Lead.budget))) or 0,
            "authority": sesion.scalar(select(func.avg(Lead.authority))) or 0,
            "need": sesion.scalar(select(func.avg(Lead.need))) or 0,
            "timeline": sesion.scalar(select(func.avg(Lead.timeline))) or 0,
        }
        por_dia = dict(
            sesion.execute(
                select(Lead.fecha, func.count(Lead.id)).group_by(Lead.fecha).order_by(Lead.fecha)
            ).all()
        )
        por_fuente = dict(
            sesion.execute(select(Lead.fuente, func.count(Lead.id)).group_by(Lead.fuente)).all()
        )
    accionables = por_clasificacion["HOT"] + por_clasificacion["WARM"]
    return {
        "total": total,
        "por_clasificacion": por_clasificacion,
        "accionables": accionables,
        "tasa_accionables": round(100 * accionables / total) if total else 0,
        "promedio_total": round(promedio_total, 1),
        "promedios_bant": {k: round(v, 1) for k, v in promedios_bant.items()},
        "por_dia": por_dia,
        "por_fuente": por_fuente,
    }
