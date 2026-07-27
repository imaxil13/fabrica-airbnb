"""
Sube el kit generado (ZIP + metadatos) a Gumroad como producto nuevo,
usando la Gumroad API. También actualiza catalogo.json para que la
próxima corrida no repita la misma combinación país+situación.

Flujo completo confirmado contra la documentacion oficial de Gumroad:
  1. POST /files/presign      -> devuelve upload_id, key, y las partes
                                  con sus presigned_url
  2. PUT a cada presigned_url -> subir cada bloque de bytes a S3,
                                  guardando el ETag de cada respuesta
  3. POST /files/complete     -> devuelve la file_url final
  4. POST /v2/products        -> crea el producto (datos basicos, precio,
                                  descripcion). Queda como borrador.
  5. PUT /v2/products/:id     -> paso separado e imprescindible: asocia
                                  el archivo al "Content" descargable del
                                  producto usando files[][url]. Sin este
                                  paso, el archivo queda solo como un
                                  adjunto de metadatos y el comprador NO
                                  recibe nada al pagar.

El producto queda "Unpublished" (borrador) a propósito: es el punto de
revisión de 30 segundos antes de que un comprador real pague por un
documento generado por IA.
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


def crear_producto_en_gumroad(kit, token):
    """Paso 4: crea el producto con los datos básicos. Todavía sin archivo
    asociado al Content — eso lo hace adjuntar_archivo_al_contenido()."""
    precio_centavos = int(float(kit["precio_sugerido"])) * 100

    campos = [
        ("access_token", token),
        ("name", kit["titulo_venta"]),
        ("description", kit["descripcion_venta"]),
        ("price", precio_centavos),
        ("customizable_price", "false"),
        ("shown_on_profile", "true"),
    ]

    respuesta = requests.post(
        f"{GUMROAD_API_BASE}/products",
        data=campos,
        timeout=60,
    )
    respuesta.raise_for_status()
    return respuesta.json()


def adjuntar_archivo_al_contenido(product_id, file_url, token):
    """Paso 5: actualiza el producto ya creado para asociar el archivo al
    Content descargable. Esta es la llamada que faltaba: sin ella, el
    archivo puede quedar registrado en Gumroad pero no aparece en la
    pestaña Content ni se entrega al comprador."""
    campos = [
        ("access_token", token),
        ("files[][url]", file_url),
    ]

    respuesta = requests.put(
        f"{GUMROAD_API_BASE}/products/{product_id}",
        data=campos,
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

    print(f"Subiendo archivo a Gumroad (presign -> S3 -> complete)...")
    file_url = subir_archivo_a_gumroad(zip_path, token)
    print(f"Archivo disponible en: {file_url}")

    print(f"Creando producto: {kit['titulo_venta']} (${kit['precio_sugerido']})")
    resultado = crear_producto_en_gumroad(kit, token)

    if not resultado.get("success"):
        raise RuntimeError(f"Gumroad rechazó la creación del producto: {resultado}")

    producto = resultado["product"]
    product_id = producto["id"]
    print(f"Producto creado (borrador): {producto.get('short_url')}")

    print("Asociando el archivo al Content descargable...")
    resultado_update = adjuntar_archivo_al_contenido(product_id, file_url, token)

    if not resultado_update.get("success"):
        raise RuntimeError(
            f"El producto se creó pero el archivo no se pudo asociar al "
            f"Content: {resultado_update}"
        )

    print("Archivo asociado correctamente al Content del producto.")

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
    print(
        "\nRECORDATORIO: el producto quedó en 'Unpublished'. Entrá a Gumroad, "
        "date un vistazo rápido al PDF en la pestaña Content, y publicá "
        "manualmente cuando estés conforme."
    )


if __name__ == "__main__":
    main()
