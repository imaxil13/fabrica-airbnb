"""
Toma el contenido generado por Groq (output/kit_generado.json) y arma
el PDF final con formato profesional, más el ZIP listo para subir a Gumroad.

Diseño fijo: se define una sola vez acá, no requiere decisiones nuevas
en cada corrida.
"""

import os
import json
import zipfile
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

OUTPUT_DIR = "output"
KIT_JSON = os.path.join(OUTPUT_DIR, "kit_generado.json")

# Paleta fija del "sello" de producto — definida una sola vez.
COLOR_PRINCIPAL = HexColor("#1B4332")   # verde oscuro, transmite seriedad/legal
COLOR_SECUNDARIO = HexColor("#40916C")
COLOR_TEXTO = HexColor("#1B1B1B")

DISCLAIMER_LEGAL = (
    "Este documento es una plantilla de referencia general y no reemplaza "
    "el asesoramiento de un abogado matriculado en tu jurisdicción. Antes "
    "de utilizarlo en una situación real, se recomienda su revisión por "
    "un profesional legal local."
)


def construir_estilos():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="TituloPortada", fontSize=26, leading=32, alignment=TA_CENTER,
        textColor=COLOR_PRINCIPAL, spaceAfter=20, fontName="Helvetica-Bold"
    ))
    styles.add(ParagraphStyle(
        name="Subtitulo", fontSize=14, leading=18, alignment=TA_CENTER,
        textColor=COLOR_SECUNDARIO, spaceAfter=30, fontName="Helvetica"
    ))
    styles.add(ParagraphStyle(
        name="EncabezadoSeccion", fontSize=16, leading=20,
        textColor=COLOR_PRINCIPAL, spaceBefore=20, spaceAfter=10,
        fontName="Helvetica-Bold"
    ))
    styles.add(ParagraphStyle(
        name="CuerpoTexto", fontSize=10.5, leading=15,
        textColor=COLOR_TEXTO, alignment=TA_LEFT, spaceAfter=8
    ))
    styles.add(ParagraphStyle(
        name="Disclaimer", fontSize=8, leading=11,
        textColor=HexColor("#666666"), alignment=TA_LEFT,
        fontName="Helvetica-Oblique"
    ))
    return styles


def texto_a_parrafos(texto, estilo):
    """Convierte texto plano con saltos de línea en una lista de Paragraphs,
    evitando que caracteres especiales rompan el render de reportlab."""
    partes = []
    for linea in texto.split("\n"):
        linea = linea.strip()
        if not linea:
            partes.append(Spacer(1, 6))
            continue
        linea_segura = (
            linea.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        partes.append(Paragraph(linea_segura, estilo))
    return partes


def armar_pdf(kit, ruta_salida):
    styles = construir_estilos()
    doc = SimpleDocTemplate(
        ruta_salida, pagesize=A4,
        topMargin=2.5 * cm, bottomMargin=2 * cm,
        leftMargin=2 * cm, rightMargin=2 * cm,
    )

    elementos = []

    # Portada
    elementos.append(Spacer(1, 4 * cm))
    elementos.append(Paragraph(kit["titulo_venta"], styles["TituloPortada"]))
    elementos.append(Paragraph(
        f"Kit para anfitriones — {kit['pais']}", styles["Subtitulo"]
    ))
    elementos.append(Spacer(1, 2 * cm))
    elementos.append(Paragraph(DISCLAIMER_LEGAL, styles["Disclaimer"]))
    elementos.append(PageBreak())

    # Documento principal
    elementos.append(Paragraph("Documento / Checklist", styles["EncabezadoSeccion"]))
    elementos.extend(texto_a_parrafos(kit["documento"], styles["CuerpoTexto"]))
    elementos.append(PageBreak())

    # Mensajes
    elementos.append(Paragraph("Mensajes listos para copiar y pegar", styles["EncabezadoSeccion"]))
    elementos.extend(texto_a_parrafos(kit["mensajes"], styles["CuerpoTexto"]))

    doc.build(elementos)


def armar_zip(kit, pdf_path, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(pdf_path, arcname=os.path.basename(pdf_path))
        # Léeme simple, siempre igual, sin necesidad de generarlo con IA.
        leeme = (
            f"{kit['titulo_venta']}\n\n"
            "Gracias por tu compra. Este kit incluye un PDF con el documento "
            "principal y los mensajes listos para usar.\n\n"
            f"{DISCLAIMER_LEGAL}\n"
        )
        zf.writestr("LEEME.txt", leeme)


def main():
    with open(KIT_JSON, "r", encoding="utf-8") as f:
        kit = json.load(f)

    nombre_base = f"{kit['pais']}_{kit['situacion']}".replace(" ", "_").lower()
    pdf_path = os.path.join(OUTPUT_DIR, f"{nombre_base}.pdf")
    zip_path = os.path.join(OUTPUT_DIR, f"{nombre_base}.zip")

    armar_pdf(kit, pdf_path)
    armar_zip(kit, pdf_path, zip_path)

    print(f"PDF generado: {pdf_path}")
    print(f"ZIP listo para subir: {zip_path}")


if __name__ == "__main__":
    main()
