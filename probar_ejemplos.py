"""Ejecuta los 3 leads de ejemplo contra el clasificador y muestra el resultado.

Uso:  python probar_ejemplos.py
Requiere ANTHROPIC_API_KEY en el entorno.
"""

import json
from pathlib import Path

from clasificador import clasificar_lead

ICONOS = {"HOT": "🔴", "WARM": "🟠", "COLD": "🟡", "DESCARTAR": "⚪"}


def main() -> None:
    for archivo in sorted((Path(__file__).parent / "ejemplos").glob("*.json")):
        lead = json.loads(archivo.read_text(encoding="utf-8"))
        print(f"\n{'=' * 70}")
        print(f"Lead: {lead['nombre']}  ({lead['fuente']})  [{archivo.name}]")
        print(f"Mensaje: {lead['mensaje_o_comentario'][:90]}...")

        resultado = clasificar_lead(lead)

        p = resultado.puntajes
        print(f"\n{ICONOS[resultado.clasificacion]} {resultado.clasificacion} — {resultado.puntaje_total}/100")
        print(f"   Budget: {p.budget} | Authority: {p.authority} | Need: {p.need} | Timeline: {p.timeline}")
        print(f"   Showroom: {resultado.showroom_recomendado}")
        print(f"   Perfil: {resultado.perfil_estimado}")
        print(f"   Señales clave: {'; '.join(resultado.señales_clave)}")
        if resultado.alertas_red_flags:
            print(f"   Red flags: {'; '.join(resultado.alertas_red_flags)}")
        print(f"   Acción: {resultado.accion_recomendada}")


if __name__ == "__main__":
    main()
