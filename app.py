import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Control Policial de Servicios", layout="wide"
)

st.title("👮‍♂️ Control y Gestión de Servicios Policiales")
st.write(
    "Sistema de control de personal y recepción de documentos operativos"
    " (Excel, PDF, Word, Imágenes)."
)
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
  st.subheader("1. Listado Base de Personal")
  file_base = st.file_uploader(
      "Sube tu personal (Excel, CSV, PDF, Word, Imágenes)",
      type=["xlsx", "xls", "csv", "pdf", "docx", "png", "jpg", "jpeg"],
      key="base",
  )

with col2:
  st.subheader("2. Orden de Servicios / Documento Superior")
  file_superior = st.file_uploader(
      "Sube órdenes (Excel, CSV, PDF, Word, Imágenes)",
      type=["xlsx", "xls", "csv", "pdf", "docx", "png", "jpg", "jpeg"],
      key="superior",
  )

if file_base is not None and file_superior is not None:
  try:
    base_name = file_base.name.lower()
    sup_name = file_superior.name.lower()

    # Validar si ambos son tabulares (Excel o CSV) para hacer el cruce automático
    is_base_tabular = base_name.endswith((".xlsx", ".xls", ".csv"))
    is_sup_tabular = sup_name.endswith((".xlsx", ".xls", ".csv"))

    if is_base_tabular and is_sup_tabular:
      # Lectura de listado base
      if base_name.endswith(".csv"):
        df_base = pd.read_csv(file_base)
      else:
        df_base = pd.read_excel(file_base)

      # Lectura de orden superior
      if sup_name.endswith(".csv"):
        df_sup = pd.read_csv(file_superior)
      else:
        df_sup = pd.read_excel(file_superior)

      df_base["Nombre"] = df_base["Nombre"].astype(str).str.strip().str.upper()
      df_sup["Nombre"] = df_sup["Nombre"].astype(str).str.strip().str.upper()

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
      st.subheader("📝 Listado General y Novedades")
      df_editado = st.data_editor(resultado, use_container_width=True)

      csv_data = df_editado.to_csv(index=False).encode("utf-8")
      st.download_button(
          label="📥 Descargar Reporte Final (CSV)",
          data=csv_data,
          file_name="reporte_policial.csv",
          mime="text/csv",
      )

    else:
      # Si alguno de los dos es PDF, Word o Imagen
      st.markdown("---")
      st.success("📁 ¡Documentos recibidos con éxito en el sistema!")

      c_info1, c_info2 = st.columns(2)
      with c_info1:
        st.info(f"**Listado Base:** {file_base.name}")
        if base_name.endswith((".png", ".jpg", ".jpeg")):
          st.image(file_base, use_container_width=True)

      with c_info2:
        st.info(f"**Orden Superior:** {file_superior.name}")
        if sup_name.endswith((".png", ".jpg", ".jpeg")):
          st.image(file_superior, use_container_width=True)

      st.warning(
          "ℹ️ Has adjuntado documentos en formato PDF, Word o Imagen. Para"
          " realizar el cruce automático de nombres y horas, recuerda que"
          " ambos archivos principales deben ser Excel (.xlsx) o CSV."
      )

  except Exception as e:
    st.error(
        f"Ocurrió un error al procesar los archivos. Asegúrate de que las"
        f" tablas contengan la columna 'Nombre'. Detalle técnico: {e}"
    )
else:
  st.info(
      "👆 Sube ambos archivos (Listado Base y Orden del Superior) para"
      " comenzar."
  )
