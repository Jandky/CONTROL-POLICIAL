import io
import pandas as pd
import pypdf
import streamlit as st

st.set_page_config(page_title="Control Policial de Servicios", layout="wide")

st.title("👮‍♂️ Control de Servicios y Horarios por Personal")
st.write(
    "Cruce directo: Identificación, Nombre, Servicio y Horas asignadas."
)
st.markdown("---")


# Función para extraer texto y asociar turnos desde PDFs
def extraer_datos_pdf(file, df_base):
  reader = pypdf.PdfReader(file)
  texto_total = ""
  for pagina in reader.pages:
    texto = pagina.extract_text()
    if texto:
      texto_total += texto + "\n"

  lineas = [l.strip() for l in texto_total.split("\n") if l.strip()]
  registros_encontrados = []

  for idx, row in df_base.iterrows():
    # Identificar la columna de nombre de forma segura
    nombre_efectivo = str(row.get("Nombre", "")).strip().upper()
    servicios_encontrados = []
    horas_encontradas = []

    for i, linea in enumerate(lineas):
      if nombre_efectivo in linea and nombre_efectivo != "":
        # Capturar contexto cercano en el PDF
        contexto = " ".join(lineas[max(0, i - 1) : min(len(lineas), i + 2)])
        servicios_encontrados.append(contexto)
        horas_encontradas.append("Ver Oficio")

    if servicios_encontrados:
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
      "Sube la orden oficial (PDF o Excel)",
      type=["xlsx", "xls", "csv", "pdf"],
      key="superior",
  )

if file_base is not None and file_superior is not None:
  try:
    # 1. Leer Listado Base
    if file_base.name.endswith(".csv"):
      df_base = pd.read_csv(file_base)
    else:
      df_base = pd.read_excel(file_base)

    # Normalizar nombres de columnas clave en el base
    # Buscamos variaciones comunes para Identificación y Nombre
    col_id = next(
        (
            c
            for c in df_base.columns
            if any(k in c.lower() for k in ["id", "cedula", "placa", "nip"])
        ),
        None,
    )
    col_nombre = next(
        (c for c in df_base.columns if "nombre" in c.lower()), df_base.columns[0]
    )

    if col_id:
      df_base = df_base.rename(columns={col_id: "Identificación"})
    else:
      df_base["Identificación"] = "-"

    df_base = df_base.rename(columns={col_nombre: "Nombre"})
    df_base["Nombre"] = df_base["Nombre"].astype(str).str.strip().str.upper()

    sup_name = file_superior.name.lower()
    df_sup = pd.DataFrame()

    # 2. Procesar documento superior
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

      # Detectar columnas de servicio y horas de forma automática
      cols_lower = [c.lower() for c in df_sup.columns]
      col_serv = next(
          (
              df_sup.columns[i]
              for i, c in enumerate(cols_lower)
              if "servicio" in c or "puesto" in c or "cargo" in c
          ),
          df_sup.columns[1] if len(df_sup.columns) > 1 else "ASIGNADO",
      )
      col_hora = next(
          (
              df_sup.columns[i]
              for i, c in enumerate(cols_lower)
              if "hora" in c or "turno" in c or "tiempo" in c
          ),
          None,
      )

      df_sup["Servicio"] = df_sup[col_serv] if col_serv in df_sup else "ASIGNADO"
      df_sup["Horas"] = df_sup[col_hora] if col_hora in df_sup else "-"

      # Agrupar si hay múltiples registros por persona
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
      st.success(f"📄 Analizando archivo PDF: **{file_superior.name}**...")
      df_sup = extraer_datos_pdf(file_superior, df_base)

    # 3. Cruce exacto uniendo por Nombre
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
    resultado["Novedad / Observación"] = ""

    # Reordenar columnas para que la Identificación y el Nombre queden al inicio, seguidos de inmediato por el Servicio y la Hora
    cols_ordenadas = ["Identificación", "Nombre", "Servicio", "Horas"]
    otras_cols = [
        c
        for c in resultado.columns
        if c not in cols_ordenadas and c != "Novedad / Observación"
    ]
    resultado = resultado[cols_ordenadas + otras_cols + ["Novedad / Observación"]]

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
    st.subheader("📝 Listado General (Identificación, Nombre, Servicio y Horas)")
    st.info(
        "💡 Al lado de la Identificación y el Nombre verás reflejado el"
        " **Servicio** y la **Hora** (si hay varios, separados por `|`). Puedes"
        " editar las novedades abajo."
    )

    # Tabla interactiva
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
        label="📥 Descargar Reporte Final (CSV)",
        data=csv_data,
        file_name="reporte_identificacion_servicios.csv",
        mime="text/csv",
    )

  except Exception as e:
    st.error(f"Error procesando los archivos: {e}")
else:
  st.info("👆 Carga tu Listado Base y tu Orden del Superior para ver el reporte.")
