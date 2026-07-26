# Fabrica de kits para anfitriones de Airbnb

Sistema automatizado que genera y publica semanalmente kits de documentos
(checklists, mensajes, plantillas) para anfitriones de alquiler temporario
en Argentina, España y México, y los sube a Gumroad automáticamente.

## Cómo queda organizado

```
fabrica-airbnb/
├── .github/workflows/pipeline.yml   <- el robot que corre solo cada semana
├── scripts/
│   ├── generar_contenido.py         <- llama a Groq (o Gemini si falla)
│   ├── fallback_gemini.py
│   ├── armar_pdf.py                 <- arma el PDF y el ZIP final
│   └── subir_gumroad.py             <- publica el producto en Gumroad
├── catalogo.json                    <- memoria: qué kits ya se hicieron
├── anuncios_pendientes.txt          <- texto ya redactado para copiar/pegar
└── requirements.txt
```

## Paso único de configuración (una sola vez)

1. Subir esta carpeta completa a un repositorio nuevo en GitHub (público o privado).
2. En el repositorio: **Settings → Secrets and variables → Actions → New repository secret**
3. Crear estos 3 secrets (el nombre debe ser exacto):
   - `GROQ_API_KEY` → tu clave de Groq
   - `GUMROAD_ACCESS_TOKEN` → tu token de Gumroad
   - `GEMINI_API_KEY` → (opcional, solo si querés el respaldo automático)

Después de esto, el sistema corre solo todos los lunes. No hace falta tocar nada más.

## Tu única tarea recurrente

Cuando el bot genera un producto nuevo, agrega el texto de anuncio al final de
`anuncios_pendientes.txt`. Ese texto ya está redactado — solo hay que copiarlo
y pegarlo en 2-3 comunidades (foros de anfitriones, grupos de Facebook/Reddit).
