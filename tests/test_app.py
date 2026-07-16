"""Pruebas de humo del demo sin consumir la API de Anthropic."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

import api
import db


class DemoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        Path("data").mkdir(exist_ok=True)
        self.temporal = tempfile.TemporaryDirectory(dir="data")
        ruta = Path(self.temporal.name) / "prueba.db"
        self.motor = create_engine(
            f"sqlite:///{ruta}", connect_args={"check_same_thread": False}
        )
        self.parche_motor = patch.object(db, "engine", self.motor)
        self.parche_entorno = patch.dict(
            os.environ,
            {
                "ANTHROPIC_API_KEY": "",
                "CLICKUP_API_TOKEN": "",
                "CLICKUP_LIST_ID": "",
                "CLICKUP_ASSIGNEE_ID": "",
                "CLICKUP_ASSIGNEES": "",
            },
        )
        self.parche_motor.start()
        self.parche_entorno.start()
        self.contexto_cliente = TestClient(api.app)
        self.cliente = self.contexto_cliente.__enter__()

    def tearDown(self) -> None:
        self.contexto_cliente.__exit__(None, None, None)
        self.parche_entorno.stop()
        self.parche_motor.stop()
        self.motor.dispose()
        self.temporal.cleanup()

    def test_arranque_siembra_y_renderiza_vistas(self) -> None:
        salud = self.cliente.get("/salud")
        self.assertEqual(salud.status_code, 200)
        cuerpo_salud = salud.json()
        self.assertEqual(cuerpo_salud["estado"], "ok")
        self.assertEqual(cuerpo_salud["leads"], 10)
        self.assertFalse(cuerpo_salud["motor_claude"])
        self.assertEqual(cuerpo_salud["base_datos"], "sqlite")
        self.assertFalse(cuerpo_salud["clickup_configurado"])
        self.assertFalse(cuerpo_salud["variables_recibidas"]["DATABASE_URL"])
        self.assertEqual(self.cliente.get("/").status_code, 200)
        self.assertEqual(self.cliente.get("/leads").status_code, 200)
        self.assertEqual(self.cliente.get("/leads/1").status_code, 200)
        self.assertEqual(self.cliente.get("/leads/9999").status_code, 404)

    def test_crear_lead_persiste_y_filtra(self) -> None:
        respuesta = self.cliente.post(
            "/api/leads",
            json={
                "fuente": "Instagram Ads",
                "fecha": "2026-07-15",
                "nombre": "Lead Integración",
                "ciudad_o_ubicacion": "Quito",
                "mensaje_o_comentario": (
                    "Soy empresario, pago de contado y quiero agendar un test drive esta semana."
                ),
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        creado = respuesta.json()
        self.assertEqual(creado["id"], 11)
        self.assertEqual(creado["motor"], "simulador")
        self.assertEqual(creado["calificacion"]["clasificacion"], "HOT")
        self.assertEqual(creado["clickup"]["estado"], "no_configurado")
        self.assertEqual(db.numero_asignacion_comercial(creado["id"]), 1)

        filtrados = self.cliente.get(
            "/api/leads", params={"clasificacion": "HOT", "q": "Integración"}
        )
        self.assertEqual(filtrados.status_code, 200)
        self.assertEqual(
            [lead["nombre"] for lead in filtrados.json()], ["Lead Integración"]
        )
        db.iniciar_db()
        self.assertEqual(db.estadisticas()["total"], 11)

    def test_rechaza_fecha_imposible(self) -> None:
        respuesta = self.cliente.post(
            "/api/leads",
            json={
                "fuente": "Formulario Web",
                "fecha": "2026-02-31",
                "nombre": "Lead Inválido",
                "mensaje_o_comentario": "Deseo información.",
            },
        )
        self.assertEqual(respuesta.status_code, 422)

    def test_sincroniza_seis_semillas_clickup_una_sola_vez(self) -> None:
        comerciales = [
            {"id": 114110475, "nombre": "Pao Barreno"},
            {"id": 87456941, "nombre": "Alan Guijarro"},
        ]

        def crear_simulado(_entrada, _calificacion, _crm, lead_id, **opciones):
            comercial = comerciales[(opciones["indice_asignacion"] - 1) % 2]
            return {
                "estado": "creado",
                "task_id": f"tarea-{lead_id}",
                "url": f"https://app.clickup.com/t/{lead_id}",
                "asignados": [comercial],
            }

        entorno = {
            "CLICKUP_API_TOKEN": "pk_prueba",
            "CLICKUP_LIST_ID": "123456",
            "CLICKUP_ASSIGNEES": "114110475:Pao Barreno,87456941:Alan Guijarro",
        }
        with patch.dict(os.environ, entorno, clear=False):
            with patch.object(api, "crear_tarea_lead", side_effect=crear_simulado) as crear:
                resultado = api._sincronizar_pendientes_clickup()
                segundo_intento = api._sincronizar_pendientes_clickup()

        self.assertEqual(resultado, {"creados": 6, "errores": 0, "pendientes": 6})
        self.assertEqual(segundo_intento["pendientes"], 0)
        self.assertEqual(crear.call_count, 6)
        self.assertEqual(
            [db.obtener_lead(lead_id).asesor for lead_id in range(1, 7)],
            ["Pao Barreno", "Alan Guijarro"] * 3,
        )

    def test_normaliza_url_de_railway_para_psycopg_3(self) -> None:
        self.assertEqual(
            db.normalizar_url_database("postgresql://usuario:clave@postgres:5432/railway"),
            "postgresql+psycopg://usuario:clave@postgres:5432/railway",
        )


if __name__ == "__main__":
    unittest.main()
