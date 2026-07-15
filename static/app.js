/* Página de captura: escenarios de ejemplo + flujo calificar → CRM → asignación. */

const escenarios = {
  hot: {
    nombre: "Andrés Villamar",
    fuente: "Instagram Ads",
    ciudad_o_ubicacion: "Samborondón",
    modelo_interes: "Lamborghini Urus",
    mensaje_o_comentario:
      "Buenas tardes, soy gerente general de un grupo inmobiliario. Busco renovar antes de fin de año. ¿Podrían coordinar un test drive esta semana? Pago de contado.",
    datos_adicionales_perfil: "CEO de grupo inmobiliario",
    telefono: "+593 99 123 4567",
    email: "demo@rosatimotors.ec",
  },
  warm: {
    nombre: "María Fernanda Ortega",
    fuente: "Formulario Web",
    ciudad_o_ubicacion: "Quito",
    modelo_interes: "Maserati Grecale",
    mensaje_o_comentario:
      "Hola, me interesa conocer más sobre financiamiento y tiempos de entrega del Grecale. Estoy evaluando comprarlo en los próximos meses.",
    datos_adicionales_perfil: "",
    telefono: "+593 98 765 4321",
    email: "mf.ortega@gmail.com",
  },
  curioso: {
    nombre: "Kevin Suárez",
    fuente: "Facebook Ads",
    ciudad_o_ubicacion: "",
    modelo_interes: "McLaren 720S",
    mensaje_o_comentario:
      "Wow que carro tan brutal 🔥 algún día tendré uno así, ¿me pueden pasar más fotos del interior?",
    datos_adicionales_perfil: "Perfil fan de autos, sin actividad profesional visible",
    telefono: "",
    email: "kevin_carslover99@hotmail.com",
  },
};

const formulario = document.getElementById("formulario-lead");
const boton = document.getElementById("boton-enviar");
const $ = (id) => document.getElementById(id);

document.querySelectorAll("[data-escenario]").forEach((chip) => {
  chip.addEventListener("click", () => {
    const datos = escenarios[chip.dataset.escenario];
    for (const [campo, valor] of Object.entries(datos)) {
      if (formulario.elements[campo]) formulario.elements[campo].value = valor;
    }
    marcarPasos(0);
  });
});

function marcarPasos(hasta) {
  for (let i = 1; i <= 4; i++) {
    $(`paso-${i}`).classList.toggle("hecho", i <= hasta);
  }
}

const NOMBRES_MOTOR = { claude: "✦ Claude (IA)", simulador: "Simulador de reglas" };

formulario.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const avisoError = $("aviso-error");
  avisoError.hidden = true;
  avisoError.textContent = "";
  const textoOriginal = boton.innerHTML;
  boton.innerHTML = '<span class="cargando"></span> Calificando…';
  boton.disabled = true;
  marcarPasos(1);

  const datos = Object.fromEntries(new FormData(formulario));
  for (const campo of ["telefono", "email", "ciudad_o_ubicacion", "modelo_interes", "datos_adicionales_perfil"]) {
    if (!datos[campo]) datos[campo] = null;
  }

  try {
    const respuesta = await fetch("/api/leads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(datos),
    });
    if (!respuesta.ok) {
      const cuerpo = await respuesta.json().catch(() => ({}));
      const detalle = typeof cuerpo.detail === "string"
        ? cuerpo.detail
        : "El servidor no pudo validar o procesar este lead.";
      throw new Error(detalle);
    }
    mostrarResultado(await respuesta.json());
  } catch (error) {
    avisoError.textContent = `No se pudo procesar el lead. ${error.message}`;
    avisoError.hidden = false;
    marcarPasos(0);
  } finally {
    boton.innerHTML = textoOriginal;
    boton.disabled = false;
  }
});

function mostrarResultado({ id, motor, calificacion, crm }) {
  $("resultado-vacio").style.display = "none";
  const resultado = $("resultado");
  resultado.classList.add("visible");
  resultado.setAttribute("tabindex", "-1");

  $("res-perfil").textContent = calificacion.perfil_estimado;
  const pastilla = $("res-clasificacion");
  pastilla.textContent = calificacion.clasificacion;
  pastilla.className = `pastilla ${calificacion.clasificacion}`;
  $("res-accion").textContent = calificacion.accion_recomendada;

  const motorEtiqueta = $("res-motor");
  motorEtiqueta.textContent = NOMBRES_MOTOR[motor] || motor;
  motorEtiqueta.className = `insignia-motor ${motor === "claude" ? "claude" : ""}`;

  animarNumero($("res-total"), calificacion.puntaje_total);

  $("res-bant").innerHTML = Object.entries(calificacion.puntajes)
    .map(
      ([dimension, puntaje]) => `
      <div class="fila-dato" title="${dimension}: ${puntaje} de 25">
        <span class="nombre">${dimension.toUpperCase()}</span>
        <div class="pista"><div class="relleno relleno-oro" style="width: 2%"></div></div>
        <span class="cifra"><b>${puntaje}</b> / 25</span>
      </div>`
    )
    .join("");
  requestAnimationFrame(() => {
    resultado.querySelectorAll("#res-bant .relleno").forEach((barra, i) => {
      const puntaje = Object.values(calificacion.puntajes)[i];
      barra.style.transition = "width .7s cubic-bezier(.2,.8,.2,1)";
      barra.style.width = `${Math.max(puntaje * 4, 2)}%`;
    });
  });

  $("res-asesor").textContent = crm.asesor;
  $("res-rol").textContent = crm.rol_asesor;
  $("res-etapa").textContent = crm.etapa;
  $("res-sla").textContent = crm.sla;
  $("res-showroom").textContent = calificacion.showroom_recomendado;
  $("res-registro").textContent = calificacion.lead_id_sugerido;
  $("res-enlace").href = `/leads/${id}`;

  marcarPasos(2);
  setTimeout(() => marcarPasos(3), 450);
  setTimeout(() => marcarPasos(4), 900);
  resultado.scrollIntoView({ behavior: "smooth", block: "nearest" });
  resultado.focus({ preventScroll: true });
}

function animarNumero(elemento, destino) {
  const duracion = 700;
  const inicio = performance.now();
  function paso(ahora) {
    const progreso = Math.min((ahora - inicio) / duracion, 1);
    const suavizado = 1 - Math.pow(1 - progreso, 3);
    elemento.textContent = Math.round(destino * suavizado);
    if (progreso < 1) requestAnimationFrame(paso);
  }
  requestAnimationFrame(paso);
}
