import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Control Policial de Servicios", layout="centered"
)

st.title("👮‍♂️ Control de Servicios Policiales")
st.write(
    "Sistema de cruce de personal y disponibilidad operativa para dispositivos"
    " móviles."
)
st.markdown("---")

st.subheader("1. Subir Listado Base")
file_base = st.file_uploader(
    "Sube tu personal (Excel o CSV con columna 'Nombre')",
    type=["xlsx", "csv"],
    key="b",
)

st.subheader("2. Subir Orden del Superior")
file_superior = st.file_uploader(
    "Sube la orden (Excel o CSV con 'Nombre', 'Servicio', 'Horas')",
    type=["xlsx", "csv"],
    key="s",
)

if file_base is not None and file_superior is not None:
  try:
    df_base = (
        pd.read_csv(file_base)
        if file_base.name.endswith(".csv")
        else pd.read_excel(file_base)
    )
    df_sup = (
        pd.read_csv(file_superior)
        if file_superior.name.endswith(".csv")
        else pd.read_excel(file_superior)
    )

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

    c1, c2, c3 = st.columns(3)
    c1.metric("Total", total)
    c2.metric("Asignados", asignados)
    c3.metric("Disponibles", disponibles)

    st.markdown("---")
    st.subheader("📝 Listado y Novedades")
    df_editado = st.data_editor(resultado, use_container_width=True)

    csv_data = df_editado.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Descargar Reporte en CSV",
        data=csv_data,
        file_name="reporte_policial.csv",
        mime="text/csv",
    )
  except Exception as e:
    st.error(
        f"Error procesando los archivos. Verifica que tengan la columna"
        f" 'Nombre'. Detalle: {e}"
    )
else:
  st.info("👆 Por favor carga ambos archivos para ver el cruce y las métricas.")