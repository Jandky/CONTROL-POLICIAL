import io
import docx
import pandas as pd
from PIL import Image
import pypdf
import pytesseract
import streamlit as st

st.set_page_config(
    page_title="Control Policial de Servicios", layout="wide"
)

st.title("👮‍♂️ Control y Gestión Avanzada de Servicios Policiales")
st.write(
    "Sistema inteligente con soporte de extracción para Excel, CSV, PDF, Word e"
    " Imágenes (OCR)."
)
st.markdown("---")


# Función inteligente para extraer texto o datos de CUALQUIER archivo
def extraer_df(file):
  filename = file.name.lower()
  lineas = []

  # 1. Excel / CSV
  if filename.endswith((".xlsx", ".xls")):
    df = pd.read_excel(file)
    return df
  elif filename.endswith(".csv"):
    df = pd.read_csv(file)
    return df

  # 2. Archivos PDF
  elif filename.endswith(".pdf"):
    reader = pypdf.PdfReader(file)
    texto_completo = ""
    for page in reader.pages:
      text = page.extract_text()
      if text:
        texto_completo += text + "\n"
    lineas = [l.strip() for l in texto_completo.split("\n") if l.strip()]
    return pd.DataFrame({"Nombre": lineas})

  # 3. Documentos de Word (.docx)
  elif filename.endswith(".docx"):
    doc = docx.Document(file)
    for p in doc.paragraphs:
      if p.text.strip():
        lineas.append(p.text.strip())
    for table in doc.tables:
      for row in table.rows:
        celdas = [cell.text.strip() for cell in row.cells if cell.text.strip()]
        if celdas:
          lineas.append(" ".join(celdas))
    return pd.DataFrame({"Nombre": lineas})

  # 4. Imágenes (PNG / JPG / JPEG) mediante OCR
  elif filename.endswith((".png", ".jpg", ".jpeg")):
    try:
      imagen = Image.open(file)
      # Extraer texto de la imagen usando OCR
      texto_ocr = pytesseract.image_to_string(imagen)
      lineas = [l.strip() for l in texto_ocr.split("\n") if l.strip()]

      # Mostrar vista previa de la imagen procesada
      st.image(
          imagen,
          caption=f"Imagen procesada por OCR: {file.name}",
          use_container_width=True,
      )
    except Exception as e:
      st.warning(
          f"No se pudo extraer texto automáticamente de la imagen {file.name}."
          f" Error: {e}"
      )

    return pd.DataFrame({"Nombre": lineas})

  return pd.DataFrame(columns=["Nombre"])


col1, col2 = st.columns(2)

with col1:
  st.subheader("1. Listado Base de Personal")
  file_base = st.file_uploader(
      "Sube personal (Excel, CSV, PDF, Word, Imagen)",
      type=["xlsx", "xls", "csv", "pdf", "docx", "png", "jpg", "jpeg"],
      key="base",
  )

with col2:
  st.subheader("2. Orden de Servicios / Documento Superior")
  file_superior = st.file_uploader(
      "Sube orden (Excel, CSV, PDF, Word, Imagen)",
      type=["xlsx", "xls", "csv", "pdf", "docx", "png", "jpg", "jpeg"],
      key="superior",
  )

if file_base is not None and file_superior is not None:
  try:
    with st.spinner(
        "Procesando y extrayendo información de los documentos..."
    ):
      df_base = extraer_df(file_base)
      df_sup = extraer_df(file_superior)

      # Asegurar formato en la columna Nombre
      if "Nombre" not in df_base.columns and not df_base.empty:
        df_base.columns = ["Nombre"] + list(df_base.columns[1:])
      if "Nombre" not in df_sup.columns and not df_sup.empty:
        df_sup.columns = ["Nombre"] + list(df_sup.columns[1:])

      if not df_base.empty:
        df_base["Nombre"] = (
            df_base["Nombre"].astype(str).str.strip().str.upper()
        )

      if not df_sup.empty:
        df_sup["Nombre"] = (
            df_sup["Nombre"].astype(str).str.strip().str.upper()
        )
        if "Servicio" not in df_sup.columns:
          df_sup["Servicio"] = "ASIGNADO (DOCUMENTO)"
        if "Horas" not in df_sup.columns:
          df_sup["Horas"] = "-"
      else:
        df_sup = pd.DataFrame(columns=["Nombre", "Servicio", "Horas"])

      # Cruce automático de datos
      resultado = pd.merge(df_base, df_sup, on="Nombre", how="left")
      resultado["Servicio"] = resultado["Servicio"].fillna("DISPONIBLE")
      resultado["Horas"] = resultado["Horas"].fillna("-")
      resultado["Novedad / Observación"] = ""

    st.markdown("---")
    st.subheader("📊 Métricas Operativas")

    total = len(df_base)
    asignados = len(resultado[resultado["Servicio"] != "DISPONIBLE"])
    disponibles = len(resultado[resultado["Servicio"] == "DISPONIBLE"])

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Personal", total)
    m2.metric("Asignados", asignados)
    m3.metric("Disponibles", disponibles)

    st.markdown("---")
    st.subheader("📝 Tabla de Resultados y Control de Novedades")
    df_editado = st.data_editor(resultado, use_container_width=True)

    csv_data = df_editado.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Descargar Reporte Final (CSV)",
        data=csv_data,
        file_name="reporte_policial_cruce.csv",
        mime="text/csv",
    )

  except Exception as e:
    st.error(f"Ocurrió un error al procesar el cruce de archivos: {e}")
else:
  st.info(
      "👆 Sube tus dos archivos en cualquier combinación (Excel, PDF, Word, Foto"
      " escaneada) para realizar el cruce automático."
  )
