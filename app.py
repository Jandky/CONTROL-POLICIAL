import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Control Policial de Servicios", layout="wide"
)

st.title("👮‍♂️ Control y Gestión de Servicios Policiales")
st.write(
    "Sistema de cruce de personal y recepción de documentos operativos (Excel,"
    " PDF, Word, Imágenes)."
)
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
  st.subheader("1. Listado Base de Personal")
  file_base = st.file_uploader(
      "Sube tu personal (Excel o CSV)", type=["xlsx", "xls", "csv"], key="base"
  )

with col2:
  st.subheader("2. Orden de Servicios / Documento Superior")
  file_superior = st.file_uploader(
      "Sube órdenes en Excel, PDF, Word o Imágenes",
      type=["xlsx", "xls", "csv", "pdf", "docx", "png", "jpg", "jpeg"],
      key="superior",
  )

if file_base is not None and file_superior is not None:
  try:
    # Lectura del listado base
    if file_base.name.endswith(".csv"):
      df_base = pd.read_csv(file_base)
    else:
      df_base = pd.read_excel(file_base)

    df_base["Nombre"] = df_base["Nombre"].astype(str).str.strip().str.upper()

    sup_name = file_superior.name.lower()

    # Validar si el superior subió un Excel/CSV para hacer cruce automático
    if sup_name.endswith((".xlsx", ".xls", ".csv")):
      if sup_name.endswith(".csv"):
        df_sup = pd.read_csv(file_superior)
      else:
        df_sup = pd.read_excel(file_superior)

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
      # Si sube PDF, Word o Imagen como orden de servicio adjunta
      st.markdown("---")
      st.success(
          f"📁 Documento adjunto recibido correctamente: **{file_superior.name}**"
      )

      if sup_name.endswith((".png", ".jpg", ".jpeg")):
        st.image(
            file_superior,
            caption="Vista previa de la orden / documento",
            use_container_width=True,
        )
      else:
        st.info(
            "El archivo PDF o Word se ha almacenado en la sesión. Para hacer"
            " el cruce automático de nombres y horas, recuerda utilizar un"
            " archivo Excel o CSV en la orden del superior."
        )

  except Exception as e:
    st.error(
        f"Ocurrió un error al procesar los archivos. Detalle técnico: {e}"
    )
else:
  st.info(
      "👆 Sube tu listado base y el documento del superior para habilitar el"
      " sistema."
  )
