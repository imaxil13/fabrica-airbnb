"""
Genera el contenido de un kit para anfitriones de alquiler temporario
usando la API de Groq (Llama 3.3 70B, gratis).

Este script:
1. Lee el catálogo para saber qué combinación país+situación falta cubrir.
2. Genera el documento principal, los scripts de mensajes y los metadatos de venta.
3. Guarda todo en /output para que el siguiente script arme el PDF.
"""

import os
import json
import time
from groq import Groq

CATALOGO_PATH = "catalogo.json"
OUTPUT_DIR = "output"

# Combinaciones país + situación que el sistema va cubriendo con el tiempo.
# Yo defino el orden; el script elige la primera que no esté en catalogo.json.
COMBINACIONES = [
    ("Argentina", "huésped que cancela de último momento"),
    ("Argentina", "daño a mobiliario durante la estadía"),
    ("España", "huésped que cancela de último momento"),
    ("España", "daño a mobiliario durante la estadía"),
    ("México", "huésped que cancela de último momento"),
    ("Argentina", "reseña negativa injusta"),
    ("España", "reseña negativa injusta"),
    ("Argentina", "ruido y quejas de vecinos"),
    ("México", "daño a mobiliario durante la estadía"),
    ("Argentina", "check-in fuera de horario"),
]


def cargar_catalogo():
    if os.path.exists(CATALOGO_PATH):
        with open(CATALOGO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"productos": []}


def elegir_combinacion_pendiente(catalogo):
    ya_hechos = {(p["pais"], p["situacion"]) for p in catalogo["productos"]}
    for pais, situacion in COMBINACIONES:
        if (pais, situacion) not in ya_hechos:
            return pais, situacion
    return None, None


def llamar_groq_con_reintentos(client, prompt, modelo="llama-3.3-70b-versatile", max_reintentos=3):
    """Llama a Groq con backoff exponencial. Si falla, se maneja en el nivel superior (fallback a Gemini)."""
    for intento in range(max_reintentos):
        try:
            respuesta = client.chat.completions.create(
                model=modelo,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=4000,
            )
            return respuesta.choices[0].message.content
        except Exception as e:
            print(f"Intento {intento + 1} fallido: {e}")
            if intento < max_reintentos - 1:
                time.sleep(2 ** intento * 15)  # 15s, 30s, 60s
            else:
                raise


def generar_kit(pais, situacion):
    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    prompt = f"""Actuá como un abogado especializado en alquileres temporarios y un experto
en atención al cliente para anfitriones de Airbnb en {pais}.

Generá un kit completo para la situación: "{situacion}".

El kit debe incluir, en formato claramente separado por secciones con encabezados ###:

### DOCUMENTO
Un documento formal (cláusula de contrato o checklist según corresponda) en español
de {pais}, listo para usar, profesional, específico y accionable. Mínimo 400 palabras.

### MENSAJES
5 mensajes distintos que el anfitrión puede copiar y pegar para comunicarse con el
huésped en esta situación, con distintos tonos (firme, conciliador, formal, breve, empático).

### TITULO_VENTA
Un título de producto atractivo para vender este kit en Gumroad (máximo 10 palabras).

### DESCRIPCION_VENTA
Una descripción de venta persuasiva de 3-4 líneas, orientada a anfitriones de Airbnb,
destacando el ahorro de tiempo y la protección legal/práctica que ofrece.

### PRECIO_SUGERIDO
Un número entre 12 y 35 (en dólares) según la complejidad del kit.

No agregues nada fuera de estas 5 secciones."""

    contenido = llamar_groq_con_reintentos(client, prompt)
    return contenido


def parsear_contenido(texto_crudo):
    """Separa el texto de Groq en las 5 secciones definidas en el prompt."""
    secciones = {}
    partes = texto_crudo.split("###")
    for parte in partes:
        parte = parte.strip()
        if not parte:
            continue
        primera_linea, *resto = parte.split("\n", 1)
        clave = primera_linea.strip().upper()
        valor = resto[0].strip() if resto else ""
        secciones[clave] = valor
    return secciones


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    catalogo = cargar_catalogo()

    pais, situacion = elegir_combinacion_pendiente(catalogo)
    if pais is None:
        print("No hay combinaciones pendientes. Agregar más en COMBINACIONES.")
        return

    print(f"Generando kit para: {pais} - {situacion}")
    texto_crudo = generar_kit(pais, situacion)
    secciones = parsear_contenido(texto_crudo)

    resultado = {
        "pais": pais,
        "situacion": situacion,
        "documento": secciones.get("DOCUMENTO", ""),
        "mensajes": secciones.get("MENSAJES", ""),
        "titulo_venta": secciones.get("TITULO_VENTA", f"Kit {situacion} - {pais}"),
        "descripcion_venta": secciones.get("DESCRIPCION_VENTA", ""),
        "precio_sugerido": secciones.get("PRECIO_SUGERIDO", "19"),
    }

    with open(os.path.join(OUTPUT_DIR, "kit_generado.json"), "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print("Contenido generado y guardado en output/kit_generado.json")


if __name__ == "__main__":
    main()
