"""
Sube el kit generado (ZIP + metadatos) a Gumroad como producto nuevo,
usando la Gumroad API. También actualiza catalogo.json para que la
próxima corrida no repita la misma combinación país+situación.

Gumroad ya no acepta el archivo directo en POST /v2/products. El flujo
correcto es:
  1. POST /files/presign      -> devuelve upload_id, key, y las partes
                                  con sus presigned_url
  2. PUT a cada presigned_url -> subir cada bloque de bytes a S3,
                                  guardando el ETag de cada respuesta
  3. POST /files/complete     -> devuelve la file_url final
  4. POST /v2/products        -> se crea el producto usando files[][url]
"""

import os
import json
import requests

OUTPUT_DIR = "output"
KIT_JSON = os.path.join(OUTPUT_DIR, "kit_generado.json")
CATALOGO_PATH = "catalogo.json"

GUMROAD_API_BASE = "https://api.gumroad.com/v2"

# Tamaño de bloque para subir a S3. 5 MB es el estándar mínimo de
# multipart upload; nuestros ZIPs son mucho más chicos, así que
# normalmente Gumroad va a devolver una sola parte.
TAMANO_PARTE_BYTES = 5 * 1024 * 1024


def cargar_catalogo():
    if os.path.exists(CATALOGO_PATH):
        with open(CATALOGO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"productos": []}


def guardar_catalogo(catalogo):
    with open(CATALOGO_PATH, "w", encoding="utf-8") as f:
        json.dump(catalogo, f, ensure_ascii=False, indent=2)


def presign_archivo(zip_path, token):
    """Paso 1: pide a Gumroad las URLs presignadas de S3 para subir el archivo."""
    nombre_archivo = os.path.basename(zip_path)
    tamano_bytes = os.path.getsize(zip_path)

    respuesta = requests.post(
        f"{GUMROAD_API_BASE}/files/presign",
        data={
            "access_token": token,
            "filename": nombre_archivo,
            "file_size": tamano_bytes,
        },
        timeout=30,
    )
    respuesta.raise_for_status()
    datos = respuesta.json()

    if "upload_id" not in datos or "parts" not in datos:
        raise RuntimeError(f"Gumroad rechazó el presign: {datos}")

    return datos  # contiene upload_id, key, parts (part_number + presigned_url)


def subir_partes_a_s3(zip_path, partes_presignadas):
    """Paso 2: sube cada bloque de bytes directamente a S3 usando las URLs
    presignadas, y guarda el ETag de cada parte para el paso de completado."""
    partes_completadas = []

    with open(zip_path, "rb") as archivo:
        for parte in partes_presignadas:
            numero_parte = parte["part_number"]
            url_presignada = parte["presigned_url"]

            bloque = archivo.read(TAMANO_PARTE_BYTES)

            respuesta_s3 = requests.put(url_presignada, data=bloque, timeout=120)
            respuesta_s3.raise_for_status()

            etag = respuesta_s3.headers.get("ETag", "").strip('"')
            if not etag:
                raise RuntimeError(
                    f"S3 no devolvió ETag para la parte {numero_parte}"
                )

            partes_completadas.append({
                "part_number": numero_parte,
                "etag": etag,
            })

    return partes_completadas


def completar_subida(upload_id, key, partes_completadas, token):
    """Paso 3: le confirma a Gumroad que todas las partes ya están en S3.

    Los campos parts[][part_number] y parts[][etag] se mandan como listas
    de tuplas (no como dict) para que requests envíe múltiples pares con
    la misma clave, que es el formato que esperan los arrays de Rails.
    """
    campos = [
        ("access_token", token),
        ("upload_id", upload_id),
        ("key", key),
    ]
    for parte in partes_completadas:
        campos.append(("parts[][part_number]", parte["part_number"]))
        campos.append(("parts[][etag]", parte["etag"]))

    respuesta = requests.post(
        f"{GUMROAD_API_BASE}/files/complete",
        data=campos,
        timeout=60,
    )
    respuesta.raise_for_status()
    datos = respuesta.json()

    if "file_url" not in datos:
        raise RuntimeError(f"Gumroad rechazó el complete: {datos}")

    return datos["file_url"]


def subir_archivo_a_gumroad(zip_path, token):
    """Ejecuta el flujo completo de 3 pasos y devuelve la file_url final."""
    presign = presign_archivo(zip_path, token)
    upload_id = presign["upload_id"]
    key = presign["key"]
    partes_presignadas = presign["parts"]

    partes_completadas = subir_partes_a_s3(zip_path, partes_presignadas)

    file_url = completar_subida(upload_id, key, partes_completadas, token)
    return file_url


def crear_producto_en_gumroad(kit, zip_path, token):
    precio_centavos = int(float(kit["precio_sugerido"])) * 100

    file_url = subir_archivo_a_gumroad(zip_path, token)

    respuesta = requests.post(
        f"{GUMROAD_API_BASE}/products",
        data={
            "access_token": token,
            "name": kit["titulo_venta"],
            "description": kit["descripcion_venta"],
            "price": precio_centavos,
            "customizable_price": "false",
            "shown_on_profile": "true",
            "files[][url]": file_url,
        },
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

    catalogo = cargar_catalogo()
    catalogo["productos"].append({
        "pais": kit["pais"],
        "situacion": kit["situacion"],
        "titulo": kit["titulo_venta"],
        "precio": kit["precio_sugerido"],
        "url": producto.get("short_url"),
    })
    guardar_catalogo(catalogo)

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
