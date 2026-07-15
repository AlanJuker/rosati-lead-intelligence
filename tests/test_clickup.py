"""Pruebas del enrutamiento comercial hacia ClickUp."""

import json
import os
import unittest
from unittest.mock import patch

import httpx

from clickup import crear_tarea_lead


ENTRADA = {
    "fuente": "Instagram Ads",
    "nombre": "Andrés Villamar",
    "telefono": "+593 99 123 4567",
    "email": "andres@example.com",
    "ciudad_o_ubicacion": "Samborondón",
    "modelo_interes": "Lamborghini Urus",
    "mensaje_o_comentario": "Pago de contado y solicito un test drive esta semana.",
}
CALIFICACION = {
    "clasificacion": "HOT",
    "puntaje_total": 97,
    "puntajes": {"budget": 25, "authority": 24, "need": 25, "timeline": 23},
    "showroom_recomendado": "Samborondón",
    "señales_clave": ["Pago de contado", "Solicita test drive"],
    "accion_recomendada": "Contactar inmediatamente",
}
CRM = {"sla": "Contactar en menos de 2 horas"}


class ClickUpTestCase(unittest.TestCase):
    def test_crea_tarea_hot_con_asignacion_y_prioridad_urgente(self) -> None:
        payload_recibido = {}

        def responder(request: httpx.Request) -> httpx.Response:
            payload_recibido.update(json.loads(request.content))
            self.assertEqual(request.headers["Authorization"], "pk_prueba")
            self.assertTrue(str(request.url).endswith("/list/123456/task"))
            return httpx.Response(
                200,
                json={"id": "abc123", "url": "https://app.clickup.com/t/abc123"},
            )

        entorno = {
            "CLICKUP_API_TOKEN": "pk_prueba",
            "CLICKUP_LIST_ID": "123456",
            "CLICKUP_ASSIGNEES": "789:Comercial Prueba",
            "CLICKUP_STATUS": "to do",
            "APP_BASE_URL": "https://demo.example.com",
        }
        with patch.dict(os.environ, entorno, clear=False):
            with httpx.Client(transport=httpx.MockTransport(responder)) as cliente:
                resultado = crear_tarea_lead(
                    ENTRADA, CALIFICACION, CRM, lead_db_id=19, client=cliente
                )

        self.assertEqual(resultado["estado"], "creado")
        self.assertEqual(resultado["task_id"], "abc123")
        self.assertEqual(payload_recibido["priority"], 1)
        self.assertEqual(payload_recibido["assignees"], [789])
        self.assertEqual(payload_recibido["status"], "to do")
        self.assertIn("https://demo.example.com/leads/19", payload_recibido["markdown_content"])

    def test_reparte_dos_leads_entre_pao_y_alan(self) -> None:
        asignaciones = []

        def responder(request: httpx.Request) -> httpx.Response:
            asignaciones.append(json.loads(request.content)["assignees"])
            numero = len(asignaciones)
            return httpx.Response(
                200,
                json={"id": f"tarea-{numero}", "url": f"https://app.clickup.com/t/{numero}"},
            )

        entorno = {
            "CLICKUP_API_TOKEN": "pk_prueba",
            "CLICKUP_LIST_ID": "123456",
            "CLICKUP_ASSIGNEES": "114110475:Pao Barreno,87456941:Alan Guijarro",
            "CLICKUP_ASSIGNMENT_MODE": "round_robin",
        }
        with patch.dict(os.environ, entorno, clear=False):
            with httpx.Client(transport=httpx.MockTransport(responder)) as cliente:
                primero = crear_tarea_lead(
                    ENTRADA, CALIFICACION, CRM, lead_db_id=1, client=cliente
                )
                segundo = crear_tarea_lead(
                    ENTRADA, CALIFICACION, CRM, lead_db_id=2, client=cliente
                )

        self.assertEqual(asignaciones, [[114110475], [87456941]])
        self.assertEqual(primero["asignados"][0]["nombre"], "Pao Barreno")
        self.assertEqual(segundo["asignados"][0]["nombre"], "Alan Guijarro")

    def test_omite_lead_cold_sin_hacer_peticion(self) -> None:
        cold = {**CALIFICACION, "clasificacion": "COLD", "puntaje_total": 40}
        resultado = crear_tarea_lead(ENTRADA, cold, CRM, lead_db_id=20)
        self.assertEqual(resultado["estado"], "omitido")

    def test_un_error_de_clickup_se_devuelve_sin_propagarse(self) -> None:
        def responder(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"err": "Token inválido"})

        with patch.dict(
            os.environ,
            {"CLICKUP_API_TOKEN": "pk_invalido", "CLICKUP_LIST_ID": "123456"},
            clear=False,
        ):
            with httpx.Client(transport=httpx.MockTransport(responder)) as cliente:
                resultado = crear_tarea_lead(
                    ENTRADA, CALIFICACION, CRM, lead_db_id=21, client=cliente
                )
        self.assertEqual(resultado["estado"], "error")


if __name__ == "__main__":
    unittest.main()
