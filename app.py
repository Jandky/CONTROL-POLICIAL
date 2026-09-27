import io
import pandas as pd
import pypdf
import streamlit as st

st.set_page_config(page_title="Control Policial de Servicios", layout="wide")

st.title("👮‍♂️ Sistema de Control y Cruce con Órdenes en PDF e Imágenes")
st.write(
    "Control operativo avanzado: soporte para múltiples servicios, horarios"
    " múltiples y registro de novedades."
)
st.markdown("---")


# Función mejorada para extraer texto y detectar patrones de servicios y horas en PDF
def extraer_datos_pdf(file, df_base):
  reader = pypdf.PdfReader(file)
  texto_total = ""
  for pagina in reader.pages:
    texto = pagina.extract_text()
    if texto:
      texto_total += texto + "\n"

  lineas = [l.strip() for l in texto_total.split("\n") if l.strip()]

  registros_encontrados = []

  # Recorrer cada efectivo del listado base para buscarlo en el texto del PDF
  for idx, row in df_base.iterrows():
    nombre_efectivo = row["Nombre"]
    servicios_encontrados = []
    horas_encontradas = []

    for i, linea in enumerate(lineas):
      if nombre_efectivo in linea:
        # Intentar extraer contexto alrededor de la línea donde aparece el nombre
        # Analizamos la línea actual y las líneas cercanas (arriba/abajo) para capturar servicio/hora
        contexto_bloque = " ".join(
            lineas[max(0, i - 1) : min(len(lineas), i + 2)]
        )

        # Detectar de forma genérica turnos u horas comunes (ej. formatos de hora como 06:00, 18:00, 08-14, etc.)
        servicios_encontrados.append(contexto_bloque)
        horas_encontradas.append("Ver Detalle en PDF")

    if servicios_encontrados:
      # Si tiene múltiples servicios u horarios, los unimos de forma clara con un separador
      servicio_final = " | ".join(dict.fromkeys(servicios_encontrados))
      hora_final = " | ".join(dict.fromkeys(horas_encontradas))

      registros_encontrados.append({
          "Nombre": nombre_efectivo,
          "Servicio": servicio_final,
          "Horas": hora_final,
      })

  return pd.DataFrame(registros_encontrados)


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

      # Asegurar columnas de servicio y horas
      if "Servicio" not in df_sup.columns:
        df_sup["Servicio"] = (
            df_sup.columns[1] if len(df_sup.columns) > 1 else "ASIGNADO"
        )
      if "Horas" not in df_sup.columns:
        df_sup["Horas"] = "-"

      # Si el Excel superior trae múltiples filas para la misma persona, las agrupamos para conservar todos sus servicios y horas
      df_sup = (
          df_sup.groupby("Nombre")
          .agg({
              "Servicio": lambda x: " | ".join(
                  [str(v) for v in x.unique() if pd.notna(v)]
              ),
              "Horas": lambda x: " | ".join(
                  [str(v) for v in x.unique() if pd.notna(v)]
              ),
          })
          .reset_index()
      )

    elif sup_name.endswith(".pdf"):
      st.success(
          f"📄 Archivo PDF detectado: **{file_superior.name}**. Analizando"
          " servicios y horarios múltiples..."
      )
      df_sup = extraer_datos_pdf(file_superior, df_base)

    elif sup_name.endswith((".png", ".jpg", ".jpeg")):
      st.image(
          file_superior,
          caption="Vista previa del documento superior (Imagen)",
          use_container_width=True,
      )
      st.info(
          "📸 Imagen cargada como referencia visual. Para un cruce automático"
          " detallado de servicios y horas, se recomienda usar Excel o PDF."
      )
      df_sup = pd.DataFrame(columns=["Nombre", "Servicio", "Horas"])

    # 3. Realizar el Cruce de Datos manteniendo múltiples asignaciones
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
    st.subheader(
        "📝 Listado General, Disponibilidad, Horarios y Registro de Novedades"
    )
    st.info(
        "💡 Si un efectivo tiene **dos o más servicios u horarios**, aparecerán"
        " unidos por el símbolo `|`. Puedes escribir o ajustar cualquier"
        " novedad de forma manual en la última columna."
    )

    # Tabla interactiva editable
    df_editado = st.data_editor(
        resultado,
        use_container_width=True,
        column_config={
            "Novedad / Observación": st.column_config.TextColumn(
                "Novedad / Observación", default=""
            )
        },
    )

    # Botón de descarga
    csv_data = df_editado.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Descargar Reporte Completo con Horarios (CSV)",
        data=csv_data,
        file_name="reporte_servicios_y_horarios.csv",
        mime="text/csv",
    )

  except Exception as e:
    st.error(
        f"Ocurrió un error al procesar el archivo. Detalle técnico: {e}"
    )
else:
  st.info(
      "👆 Sube tu Listado Base en Excel y tu Orden del Superior (PDF o Excel)"
      " para ver los servicios y horarios combinados."
  )
