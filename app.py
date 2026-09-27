import io
import pandas as pd
import pypdf
import streamlit as st

st.set_page_config(page_title="Control Policial de Servicios", layout="wide")

st.title("👮‍♂️ Sistema de Control y Cruce con Órdenes en PDF e Imágenes")
st.write(
    "Sube tu Listado Base (Excel/CSV) y tu Orden de Servicio en PDF o Excel"
    " para realizar el cruce automático y control de novedades."
)
st.markdown("---")


# Función para extraer texto de un PDF y buscar nombres o líneas operativas
def extraer_texto_pdf(file):
  reader = pypdf.PdfReader(file)
  texto_total = ""
  for pagina in reader.pages:
    texto = pagina.extract_text()
    if texto:
      texto_total += texto + "\n"

  # Limpiar y separar por líneas
  lineas = [l.strip() for l in texto_total.split("\n") if l.strip()]
  return lineas


col1, col2 = st.columns(2)

with col1:
  st.subheader("1. Listado Base de Personal")
  file_base = st.file_uploader(
      "Sube tu personal a cargo (Excel o CSV)",
      type=["xlsx", "xls", "csv"],
      key="base",
  )

with col2:
  st.subheader("2. Orden del Superior (PDF o Excel)")
  file_superior = st.file_uploader(
      "Sube la orden oficial (PDF, Excel, CSV o Imagen)",
      type=["xlsx", "xls", "csv", "pdf", "png", "jpg", "jpeg"],
      key="superior",
  )

if file_base is not None and file_superior is not None:
  try:
    # 1. Leer Listado Base
    if file_base.name.endswith(".csv"):
      df_base = pd.read_csv(file_base)
    else:
      df_base = pd.read_excel(file_base)

    # Normalizar columna de nombres del listado base
    col_base_nombre = next(
        (c for c in df_base.columns if "nombre" in c.lower()), df_base.columns[0]
    )
    df_base = df_base.rename(columns={col_base_nombre: "Nombre"})
    df_base["Nombre"] = df_base["Nombre"].astype(str).str.strip().str.upper()

    sup_name = file_superior.name.lower()
    df_sup = pd.DataFrame()

    # 2. Procesar según el formato del documento superior
    if sup_name.endswith((".xlsx", ".xls", ".csv")):
      if sup_name.endswith(".csv"):
        df_sup = pd.read_csv(file_superior)
      else:
        df_sup = pd.read_excel(file_superior)

      col_sup_nombre = next(
          (c for c in df_sup.columns if "nombre" in c.lower()), df_sup.columns[0]
      )
      df_sup = df_sup.rename(columns={col_sup_nombre: "Nombre"})
      df_sup["Nombre"] = df_sup["Nombre"].astype(str).str.strip().str.upper()

      if "Servicio" not in df_sup.columns:
        df_sup["Servicio"] = (
            df_sup.columns[1] if len(df_sup.columns) > 1 else "ASIGNADO"
        )
      if "Horas" not in df_sup.columns:
        df_sup["Horas"] = "-"

    elif sup_name.endswith(".pdf"):
      st.success(
          f"📄 Archivo PDF detectado: **{file_superior.name}**. Extrayendo"
          " texto y buscando coincidencias..."
      )
      lineas_pdf = extraer_texto_pdf(file_superior)

      # Cruce inteligente: revisa si el nombre del personal base aparece escrito dentro del texto del PDF
      nombres_en_pdf = []
      for idx, row in df_base.iterrows():
        nombre_efectivo = row["Nombre"]
        # Buscar si el nombre completo del efectivo aparece en alguna línea del PDF
        encontrado = any(nombre_efectivo in linea for linea in lineas_pdf)
        if encontrado:
          nombres_en_pdf.append({
              "Nombre": nombre_efectivo,
              "Servicio": "ASIGNADO SEGÚN PDF",
              "Horas": "Ver Oficio",
          })

      df_sup = pd.DataFrame(nombres_en_pdf)
      if df_sup.empty:
        st.warning(
            "⚠️ No se encontraron coincidencias exactas de nombres del listado"
            " base dentro del texto del PDF. Asegúrate de que los nombres en el"
            " Excel coincidan con los del documento."
        )
        df_sup = pd.DataFrame(columns=["Nombre", "Servicio", "Horas"])

    elif sup_name.endswith((".png", ".jpg", ".jpeg")):
      st.image(
          file_superior,
          caption="Vista previa del documento superior (Imagen)",
          use_container_width=True,
      )
      st.info(
          "📸 Imagen cargada como referencia visual. Para un cruce automático"
          " exacto de nombres de personal, se recomienda utilizar el archivo"
          " oficial en PDF o Excel."
      )
      df_sup = pd.DataFrame(columns=["Nombre", "Servicio", "Horas"])

    # 3. Realizar el Cruce de Datos (Merge)
    if not df_sup.empty and "Nombre" in df_sup.columns:
      resultado = pd.merge(
          df_base,
          df_sup[["Nombre", "Servicio", "Horas"]],
          on="Nombre",
          how="left",
      )
    else:
      resultado = df_base.copy()
      resultado["Servicio"] = "DISPONIBLE"
      resultado["Horas"] = "-"

    resultado["Servicio"] = resultado["Servicio"].fillna("DISPONIBLE")
    resultado["Horas"] = resultado["Horas"].fillna("-")

    if "Novedad / Observación" not in resultado.columns:
      resultado["Novedad / Observación"] = ""

    st.markdown("---")
    st.subheader("📊 Métricas Operativas de Fuerza")

    total = len(df_base)
    asignados = len(resultado[resultado["Servicio"] != "DISPONIBLE"])
    disponibles = len(resultado[resultado["Servicio"] == "DISPONIBLE"])

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Personal a Cargo", total)
    m2.metric("Asignados a Servicio", asignados)
    m3.metric("Disponibles en Base", disponibles)

    st.markdown("---")
    st.subheader("📝 Listado General, Disponibilidad y Registro de Novedades")
    st.info(
        "💡 Puedes escribir o editar directamente en la columna **'Novedad /"
        " Observación'** (permisos, excusas, etc.)."
    )

    # Tabla interactiva editable para novedades
    df_editado = st.data_editor(
        resultado,
        use_container_width=True,
        column_config={
            "Novedad / Observación": st.column_config.TextColumn(
                "Novedad / Observación", default=""
            )
        },
    )

    # Botón de descarga del reporte final
    csv_data = df_editado.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Descargar Reporte Final de Novedades (CSV)",
        data=csv_data,
        file_name="reporte_novedades_oficial.csv",
        mime="text/csv",
    )

  except Exception as e:
    st.error(
        f"Ocurrió un error al procesar la lectura de los archivos. Detalle: {e}"
    )
else:
  st.info(
      "👆 Sube tu Listado Base en Excel/CSV y tu Orden del Superior (en PDF o"
      " Excel) para generar el cruce automático."
  )
