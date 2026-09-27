import io
import pandas as pd
import pypdf
import streamlit as st

st.set_page_config(page_title="Control Policial de Servicios", layout="wide")

st.title("👮‍♂️ Control de Servicios y Horarios por Personal")
st.write(
    "Reporte limpio: Grado, Nombre, Identificación, Servicio y Hora"
    " correspondientes a tu personal."
)
st.markdown("---")


# Función limpia para extraer texto de PDF sin alterar ni agregar personas ajenas
def buscar_en_pdf(file, df_base):
  reader = pypdf.PdfReader(file)
  texto_total = ""
  for pagina in reader.pages:
    texto = pagina.extract_text()
    if texto:
      texto_total += texto + "\n"

  lineas = [l.strip() for l in texto_total.split("\n") if l.strip()]
  servicios_dict = {}
  horas_dict = {}

  # Solo buscamos los nombres que EXACTAMENTE están en tu listado base
  for idx, row in df_base.iterrows():
    nombre_efectivo = str(row.get("Nombre", "")).strip().upper()
    if not nombre_efectivo:
      continue

    servicios_encontrados = []
    horas_encontradas = []

    for i, linea in enumerate(lineas):
      if nombre_efectivo in linea:
        # Extraer contexto inmediato (la línea del nombre y la siguiente por si ahí está el servicio/hora)
        bloque = " ".join(lineas[i : min(len(lineas), i + 2)])
        servicios_encontrados.append(bloque)
        horas_encontradas.append("Ver Oficio")

    if servicios_encontrados:
      servicios_dict[nombre_efectivo] = " | ".join(
          dict.fromkeys(servicios_encontrados)
      )
      horas_dict[nombre_efectivo] = " | ".join(
          dict.fromkeys(horas_encontradas)
      )
    else:
      servicios_dict[nombre_efectivo] = "DISPONIBLE"
      horas_dict[nombre_efectivo] = "-"

  return servicios_dict, horas_dict


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
    # 1. Cargar Listado Base
    if file_base.name.endswith(".csv"):
      df_base = pd.read_csv(file_base)
    else:
      df_base = pd.read_excel(file_base)

    # Identificar columnas clave en el base de forma inteligente
    cols_lower = [str(c).lower() for c in df_base.columns]

    col_grado = next(
        (
            df_base.columns[i]
            for i, c in enumerate(cols_lower)
            if "grado" in c or "jerarquia" in c or "rango" in c
        ),
        None,
    )
    col_nombre = next(
        (
            df_base.columns[i]
            for i, c in enumerate(cols_lower)
            if "nombre" in c or "apellidos" in c
        ),
        df_base.columns[0],
    )
    col_id = next(
        (
            df_base.columns[i]
            for i, c in enumerate(cols_lower)
            if any(k in c for k in ["id", "cedula", "placa", "nip"])
        ),
        None,
    )

    # Construir un DataFrame limpio estructurado exclusivamente con el personal base
    df_resultado = pd.DataFrame()
    df_resultado["Grado"] = (
        df_base[col_grado].astype(str).str.strip().str.upper()
        if col_grado
        else "-"
    )
    df_resultado["Nombre"] = (
        df_base[col_nombre].astype(str).str.strip().str.upper()
    )
    df_resultado["Identificación"] = (
        df_base[col_id].astype(str).str.strip() if col_id else "-"
    )

    sup_name = file_superior.name.lower()

    # 2. Procesar documento superior y mapear estrictamente al personal base
    if sup_name.endswith((".xlsx", ".xls", ".csv")):
      if sup_name.endswith(".csv"):
        df_sup = pd.read_csv(file_superior)
      else:
        df_sup = pd.read_excel(file_superior)

      sup_cols_lower = [str(c).lower() for c in df_sup.columns]
      col_sup_nombre = next(
          (df_sup.columns[i] for i, c in enumerate(sup_cols_lower) if "nombre" in c),
          df_sup.columns[0],
      )
      col_sup_serv = next(
          (
              df_sup.columns[i]
              for i, c in enumerate(sup_cols_lower)
              if "servicio" in c or "puesto" in c or "cargo" in c
          ),
          df_sup.columns[1] if len(df_sup.columns) > 1 else "ASIGNADO",
      )
      col_sup_hora = next(
          (
              df_sup.columns[i]
              for i, c in enumerate(sup_cols_lower)
              if "hora" in c or "turno" in c
          ),
          None,
      )

      df_sup["Nombre_Clean"] = (
          df_sup[col_sup_nombre].astype(str).str.strip().str.upper()
      )
      df_sup["Servicio_Clean"] = (
          df_sup[col_sup_serv].astype(str).str.strip()
          if col_sup_serv in df_sup
          else "ASIGNADO"
      )
      df_sup["Hora_Clean"] = (
          df_sup[col_sup_hora].astype(str).str.strip()
          if col_sup_hora and col_sup_hora in df_sup
          else "-"
      )

      # Agrupar si un efectivo tiene múltiples filas en el Excel superior
      df_sup_agrupado = (
          df_sup.groupby("Nombre_Clean")
          .agg({
              "Servicio_Clean": lambda x: " | ".join(
                  [str(v) for v in x.unique() if pd.notna(v) and v != "nan"]
              ),
              "Hora_Clean": lambda x: " | ".join(
                  [str(v) for v in x.unique() if pd.notna(v) and v != "nan"]
              ),
          })
          .reset_index()
      )

      # Hacer merge exacto basado en el nombre del personal base
      df_resultado = pd.merge(
          df_resultado,
          df_sup_agrupado,
          left_on="Nombre",
          right_on="Nombre_Clean",
          how="left",
      )
      df_resultado["Servicio"] = df_resultado["Servicio_Clean"].fillna(
          "DISPONIBLE"
      )
      df_resultado["Horas"] = df_resultado["Hora_Clean"].fillna("-")

      # Limpiar columnas temporales de control
      cols_a_borrar = [
          c
          for c in ["Nombre_Clean", "Servicio_Clean", "Hora_Clean"]
          if c in df_resultado.columns
      ]
      df_resultado = df_resultado.drop(columns=cols_a_borrar)

    elif sup_name.endswith(".pdf"):
      st.success(
          f"📄 Procesando PDF: **{file_superior.name}** y cruzando"
          " exclusivamente con tu personal base..."
      )
      dic_servicios, dic_horas = buscar_en_pdf(file_superior, df_resultado)

      df_resultado["Servicio"] = df_resultado["Nombre"].map(dic_servicios).fillna("DISPONIBLE")
      df_resultado["Horas"] = df_resultado["Nombre"].map(dic_horas).fillna("-")

    # Agregar columna vacía para novedades editables al final
    df_resultado["Novedad / Observación"] = ""

    # Orden exacto y limpio solicitado: Grado, Nombre, Identificación, Servicio, Horas, Novedad
    columnas_finales = [
        "Grado",
        "Nombre",
        "Identificación",
        "Servicio",
        "Horas",
        "Novedad / Observación",
    ]
    # Asegurar que solo contenga esas columnas limpias
    for c in columnas_finales:
      if c not in df_resultado.columns:
        df_resultado[c] = "-"
    df_resultado = df_resultado[columnas_finales]

    st.markdown("---")
    st.subheader("📊 Métricas Operativas")
    total = len(df_resultado)
    asignados = len(df_resultado[df_resultado["Servicio"] != "DISPONIBLE"])
    disponibles = len(df_resultado[df_resultado["Servicio"] == "DISPONIBLE"])

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Personal Base", total)
    m2.metric("Asignados en Orden", asignados)
    m3.metric("Disponibles", disponibles)

    st.markdown("---")
    st.subheader("📝 Reporte Ordenado de Personal y Servicios")
    st.info(
        "💡 Este listado respeta estrictamente a tu personal base. Al lado de"
        " la identificación encontrarás ordenadamente su **Grado, Nombre,"
        " Servicio y Hora**."
    )

    # Tabla interactiva limpia
    df_editado = st.data_editor(
        df_resultado,
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
        label="📥 Descargar Reporte Limpio y Ordenado (CSV)",
        data=csv_data,
        file_name="reporte_servicios_ordenado.csv",
        mime="text/csv",
    )

  except Exception as e:
    st.error(
        f"Ocurrió un error al procesar el reporte ordenado. Detalle técnico: {e}"
    )
else:
  st.info(
      "👆 Carga tu Listado Base y tu Orden del Superior para generar el reporte"
      " limpio."
  )
