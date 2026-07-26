"""
Fallback: si Groq falla después de 3 reintentos, este módulo genera
el mismo contenido usando Google AI Studio (Gemini), que tiene mayor
volumen diario gratis.

Se importa desde generar_contenido.py solo si es necesario.
"""

import os
import google.generativeai as genai


def generar_con_gemini(prompt):
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    modelo = genai.GenerativeModel("gemini-1.5-flash")
    respuesta = modelo.generate_content(prompt)
    return respuesta.text
