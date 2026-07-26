"""
Sube el kit generado (ZIP + metadatos) a Gumroad como producto nuevo,
usando la Gumroad API. También actualiza catalogo.json para que la
próxima corrida no repita la misma combinación país+situación.
"""

import os
import json
import requests

OUTPUT_DIR = "output"
KIT_JSON = os.path.join(OUTPUT_DIR, "kit_generado.json")
CATALOGO_PATH = "catalogo.json"

GUMROAD_API_BASE = "https://api.gumroad.com/v2"


def cargar_catalogo():
    if os.path.exists(CATALOGO_PATH):
        with open(CATALOGO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"productos": []}


def guardar_catalogo(catalogo):
    with open(CATALOGO_PATH, "w", encoding="utf-8") as f:
        json.dump(catalogo, f, ensure_ascii=False, indent=2)


def crear_producto_en_gumroad(kit, zip_path, token):
    precio_centavos = int(float(kit["precio_sugerido"])) * 100

    with open(zip_path, "rb") as archivo:
        respuesta = requests.post(
            f"{GUMROAD_API_BASE}/products",
            data={
                "access_token": token,
                "name": kit["titulo_venta"],
                "description": kit["descripcion_venta"],
                "price": precio_centavos,
                "customizable_price": "false",
                "shown_on_profile": "true",
            },
            files={"file": archivo},
            timeout=60,
        )

    respuesta.raise_for_status()
    return respuesta.json()


def main():
    token = os.environ["GUMROAD_ACCESS_TOKEN"]

    with open(KIT_JSON, "r", encoding="utf-8") as f:
        kit = json.load(f)

    nombre_base = f"{kit['pais']}_{kit['situacion']}".replace(" ", "_").lower()
    zip_path = os.path.join(OUTPUT_DIR, f"{nombre_base}.zip")

    print(f"Subiendo a Gumroad: {kit['titulo_venta']} (${kit['precio_sugerido']})")
    resultado = crear_producto_en_gumroad(kit, zip_path, token)

    if not resultado.get("success"):
        raise RuntimeError(f"Gumroad rechazó la subida: {resultado}")

    producto = resultado["product"]
    print(f"Publicado: {producto.get('short_url')}")

    # Actualizar catálogo para no repetir esta combinación
    catalogo = cargar_catalogo()
    catalogo["productos"].append({
        "pais": kit["pais"],
        "situacion": kit["situacion"],
        "titulo": kit["titulo_venta"],
        "precio": kit["precio_sugerido"],
        "url": producto.get("short_url"),
    })
    guardar_catalogo(catalogo)

    # Dejar preparado el texto de anuncio para que el único paso humano
    # sea copiar y pegar, no redactar nada.
    texto_anuncio = (
        f"Nuevo: {kit['titulo_venta']}\n\n"
        f"{kit['descripcion_venta']}\n\n"
        f"Disponible acá: {producto.get('short_url')}"
    )
    with open("anuncios_pendientes.txt", "a", encoding="utf-8") as f:
        f.write(texto_anuncio + "\n\n---\n\n")

    print("Catálogo actualizado y anuncio agregado a anuncios_pendientes.txt")


if __name__ == "__main__":
    main()
