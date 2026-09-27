import io
import re
import unicodedata

import pandas as pd
import pdfplumber
import streamlit as st


st.set_page_config(
    page_title="Control Policial de Servicios",
    page_icon="👮",
    layout="wide",
)

st.title("👮 Control de Servicios y Horarios por Personal")
st.write(
    "Cruza tu listado base con una orden en Excel, CSV o PDF. "
    "El reporte solo incluye personas del listado base."
)
st.markdown("---")


COLUMNAS_FINALES = [
    "Grado",
    "Nombre",
    "Identificación",
    "Servicio",
    "Horas",
    "Novedad / Observación",
]

ESTADOS_REVISION = {
    "REVISAR PDF",
    "REVISAR SERVICIO",
    "REVISAR: VARIAS ASIGNACIONES",
    "REVISAR ORDEN",
}


def texto_limpio(valor):
    """Convierte valores vacíos en cadena vacía y elimina espacios sobrantes."""
    if valor is None or pd.isna(valor):
        return ""

    return " ".join(str(valor).split()).strip()


def normalizar(valor):
    """Normaliza texto para comparar nombres sin depender de tildes o espacios."""
    texto = texto_limpio(valor).upper()
    texto = unicodedata.normalize("NFKD", texto)

    texto = "".join(
        caracter
        for caracter in texto
        if not unicodedata.combining(caracter)
    )

    return " ".join(texto.split())


def buscar_columna(columnas, opciones):
    """Encuentra la primera columna cuyo nombre contiene alguna opción."""
    for columna in columnas:
        nombre = normalizar(columna)

        if any(opcion in nombre for opcion in opciones):
            return columna

    return None


def leer_archivo_tabular(archivo):
    """Lee Excel o CSV procurando conservar identificaciones como texto."""
    nombre = archivo.name.lower()
    archivo.seek(0)

    if nombre.endswith(".csv"):
        contenido = archivo.getvalue()
        ultimo_error = None

        for codificacion in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return pd.read_csv(
                    io.BytesIO(contenido),
                    encoding=codificacion,
                    sep=None,
                    engine="python",
                    dtype=str,
                    keep_default_na=False,
                )
            except (UnicodeDecodeError, pd.errors.ParserError) as error:
                ultimo_error = error

        raise ValueError(
            f"No fue posible leer el CSV. Detalle: {ultimo_error}"
        )

    return pd.read_excel(
        archivo,
        dtype=str,
        keep_default_na=False,
    )


def preparar_base(df_base):
    """Construye el reporte únicamente con las personas del archivo base."""
    if df_base.empty:
        raise ValueError("El listado base está vacío.")

    columnas = list(df_base.columns)

    col_grado = buscar_columna(
        columnas, ("GRADO", "JERARQUIA", "RANGO")
    )
    col_nombre = buscar_columna(
        columnas, ("NOMBRE", "APELLIDO")
    )
    col_id = buscar_columna(
        columnas,
        (
            "IDENTIFICACION",
            "CEDULA",
            "DOCUMENTO",
            "PLACA",
            "NIP",
        ),
    )

    if col_nombre is None:
        raise ValueError(
            "No encontré una columna de nombres en el listado base. "
            "Ponle un encabezado que contenga 'Nombre' o 'Apellidos'."
        )

    resultado = pd.DataFrame(index=df_base.index)

    resultado["Grado"] = (
        df_base[col_grado].map(texto_limpio)
        if col_grado is not None
        else "-"
    )

    resultado["Nombre"] = df_base[col_nombre].map(texto_limpio)

    resultado["Identificación"] = (
        df_base[col_id].map(texto_limpio)
        if col_id is not None
        else "-"
    )

    resultado = resultado.loc[
        resultado["Nombre"].map(normalizar).ne("")
    ].copy()

    if resultado.empty:
        raise ValueError(
            "El listado base no contiene nombres válidos."
        )

    resultado["Grado"] = resultado["Grado"].replace("", "-")
    resultado["Identificación"] = resultado[
        "Identificación"
    ].replace("", "-")

    resultado["Nombre"] = resultado["Nombre"].str.upper()
    resultado["Nombre_clave"] = resultado["Nombre"].map(normalizar)

    return resultado.reset_index(drop=True)


def preparar_orden_tabular(df_orden):
    """Lee asignaciones cuando la orden viene en Excel o CSV."""
    if df_orden.empty:
        raise ValueError("La orden está vacía.")

    columnas = list(df_orden.columns)

    col_nombre = buscar_columna(
        columnas, ("NOMBRE", "APELLIDO")
    )
    col_servicio = buscar_columna(
        columnas, ("SERVICIO", "PUESTO", "CARGO")
    )
    col_hora = buscar_columna(
        columnas, ("HORA", "HORARIO", "TURNO")
    )

    if col_nombre is None:
        raise ValueError(
            "La orden Excel/CSV debe tener una columna con "
            "'Nombre' o 'Apellidos'."
        )

    asignaciones = {}

    for _, fila in df_orden.iterrows():
        nombre = normalizar(fila[col_nombre])

        if not nombre:
            continue

        servicio = (
            texto_limpio(fila[col_servicio])
            if col_servicio is not None
            else ""
        )
        hora = (
            texto_limpio(fila[col_hora])
            if col_hora is not None
            else ""
        )

        asignaciones.setdefault(nombre, []).append(
            (servicio, hora)
        )

    return asignaciones


def nombre_en_celda(nombre_normalizado, contenido_celda):
    """Busca el nombre completo sin aceptar coincidencias parciales."""
    celda = normalizar(contenido_celda)

    if not celda:
        return False

    patron = (
        rf"(?<!\w){re.escape(nombre_normalizado)}(?!\w)"
    )

    return re.search(patron, celda) is not None


def indice_columna(encabezados, opciones):
    """Busca un índice de columna a partir de sus encabezados."""
    for indice, encabezado in enumerate(encabezados):
        texto = normalizar(encabezado)

        if any(opcion in texto for opcion in opciones):
            return indice

    return None


def obtener_celda(fila, indice):
    if indice is None or indice >= len(fila):
        return ""

    return texto_limpio(fila[indice])


def extraer_asignaciones_pdf(archivo, nombres_base):
    """
    Extrae asignaciones solo cuando nombre, servicio y hora
    se pueden asociar a columnas de una misma fila.
    """
    asignaciones = {
        nombre: []
        for nombre in nombres_base
    }

    diagnostico = []
    paginas_con_texto = 0
    cantidad_tablas = 0
    tablas_con_nombres = 0

    archivo.seek(0)

    with pdfplumber.open(archivo) as pdf:
        for numero_pagina, pagina in enumerate(
            pdf.pages, start=1
        ):
            texto_pagina = pagina.extract_text() or ""

            if texto_pagina.strip():
                paginas_con_texto += 1

            tablas = pagina.extract_tables()

            for numero_tabla, tabla in enumerate(
                tablas, start=1
            ):
                if not tabla:
                    continue

                cantidad_tablas += 1

                # Una muestra ayuda a diagnosticar cómo se leyó el PDF.
                for fila in tabla[:8]:
                    diagnostico.append({
                        "Página": numero_pagina,
                        "Tabla": numero_tabla,
                        "Celdas extraídas": " || ".join(
                            texto_limpio(celda)
                            for celda in fila
                        ),
                    })

                posicion_encabezado = None
                columnas_encontradas = None

                # Algunos PDF tienen título antes del encabezado.
                for posicion, fila in enumerate(
                    tabla[:min(6, len(tabla))]
                ):
                    encabezados = [
                        texto_limpio(celda)
                        for celda in fila
                    ]

                    idx_nombre = indice_columna(
                        encabezados,
                        ("NOMBRE", "APELLIDO"),
                    )

                    idx_servicio = indice_columna(
                        encabezados,
                        ("SERVICIO", "PUESTO", "CARGO"),
                    )

                    idx_hora = indice_columna(
                        encabezados,
                        ("HORA", "HORARIO", "TURNO"),
                    )

                    if idx_nombre is not None:
                        posicion_encabezado = posicion
                        columnas_encontradas = (
                            idx_nombre,
                            idx_servicio,
                            idx_hora,
                        )
                        break

                if posicion_encabezado is None:
                    continue

                tablas_con_nombres += 1

                (
                    idx_nombre,
                    idx_servicio,
                    idx_hora,
                ) = columnas_encontradas

                for fila in tabla[
                    posicion_encabezado + 1:
                ]:
                    if not fila:
                        continue

                    celda_nombre = obtener_celda(
                        fila, idx_nombre
                    )

                    candidatos = [
                        nombre
                        for nombre in nombres_base
                        if nombre_en_celda(
                            nombre, celda_nombre
                        )
                    ]

                    # Si la celda parece contener varios efectivos,
                    # no se asigna el servicio a ninguno.
                    if len(candidatos) != 1:
                        continue

                    nombre = candidatos[0]

                    servicio = obtener_celda(
                        fila, idx_servicio
                    )
                    hora = obtener_celda(
                        fila, idx_hora
                    )

                    asignaciones[nombre].append(
                        (servicio, hora)
                    )

    datos_diagnostico = {
        "paginas_con_texto": paginas_con_texto,
        "cantidad_tablas": cantidad_tablas,
        "tablas_con_nombres": tablas_con_nombres,
        "muestra": pd.DataFrame(diagnostico),
    }

    return asignaciones, datos_diagnostico


def asignar_resultados(df_base, asignaciones):
    """
    Conserva todas las filas del personal base.
    Nunca agrega personas procedentes de la orden.
    """
    resultado = df_base.copy()

    servicios = []
    horas = []

    for nombre in resultado["Nombre_clave"]:
        registros = list(
            dict.fromkeys(asignaciones.get(nombre, []))
        )

        if len(registros) == 0:
            servicios.append("REVISAR ORDEN")
            horas.append("REVISAR ORDEN")
            continue

        if len(registros) > 1:
            servicios.append(
                "REVISAR: VARIAS ASIGNACIONES"
            )
            horas.append("REVISAR ORDEN")
            continue

        servicio, hora = registros[0]

        servicios.append(
            servicio if servicio else "REVISAR SERVICIO"
        )
        horas.append(
            hora if hora else "REVISAR HORA"
        )

    resultado["Servicio"] = servicios
    resultado["Horas"] = horas
    resultado["Novedad / Observación"] = ""

    return resultado[COLUMNAS_FINALES]


col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Listado base de personal")

    file_base = st.file_uploader(
        "Sube tu personal a cargo",
        type=["xlsx", "xls", "csv"],
        key="base",
    )

with col2:
    st.subheader("2. Orden del superior")

    file_superior = st.file_uploader(
        "Sube la orden oficial",
        type=["xlsx", "xls", "csv", "pdf"],
        key="superior",
    )


if file_base is None or file_superior is None:
    st.info(
        "👆 Carga el listado base y la orden para generar "
        "el reporte."
    )

else:
    try:
        df_base_original = leer_archivo_tabular(
            file_base
        )
        df_base = preparar_base(
            df_base_original
        )

        nombre_orden = file_superior.name.lower()
        diagnostico_pdf = None

        if nombre_orden.endswith(".pdf"):
            asignaciones, diagnostico_pdf = (
                extraer_asignaciones_pdf(
                    file_superior,
                    set(df_base["Nombre_clave"]),
                )
            )

            if (
                diagnostico_pdf["paginas_con_texto"]
                == 0
            ):
                st.error(
                    "El PDF no contiene texto extraíble. "
                    "Puede ser un documento escaneado; "
                    "en ese caso se necesita OCR."
                )

            elif (
                diagnostico_pdf["cantidad_tablas"]
                == 0
            ):
                st.warning(
                    "El PDF tiene texto, pero no se "
                    "detectaron tablas. Las asignaciones "
                    "quedarán para revisión."
                )

            elif (
                diagnostico_pdf["tablas_con_nombres"]
                == 0
            ):
                st.warning(
                    "Se detectaron tablas, pero no una "
                    "columna identificable como 'Nombre'. "
                    "Revisa el diagnóstico del PDF."
                )

        else:
            df_orden = leer_archivo_tabular(
                file_superior
            )
            asignaciones = preparar_orden_tabular(
                df_orden
            )

        df_resultado = asignar_resultados(
            df_base,
            asignaciones,
        )

        st.markdown("---")
        st.subheader("📊 Métricas operativas")

        es_pendiente = (
            df_resultado["Servicio"]
            .isin(ESTADOS_REVISION)
        ) | (
            df_resultado["Horas"]
            .isin({"REVISAR ORDEN", "REVISAR HORA"})
        )

        es_disponible = (
            df_resultado["Servicio"]
            .map(normalizar)
            .eq("DISPONIBLE")
        ) & ~es_pendiente

        total = len(df_resultado)
        pendientes = int(es_pendiente.sum())
        disponibles = int(es_disponible.sum())
        asignados = (
            total - pendientes - disponibles
        )

        m1, m2, m3, m4 = st.columns(4)

        m1.metric("Personal base", total)
        m2.metric(
            "Asignados confirmados",
            asignados,
        )
        m3.metric("Disponibles", disponibles)
        m4.metric(
            "Pendientes de revisión",
            pendientes,
        )

        st.markdown("---")
        st.subheader(
            "📝 Reporte de personal y servicios"
        )

        st.info(
            "El reporte incluye exclusivamente personal "
            "del listado base. 'REVISAR' indica que no se "
            "pudo confirmar el dato automáticamente; "
            "no significa que el efectivo esté disponible."
        )

        df_editado = st.data_editor(
            df_resultado,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "Novedad / Observación": (
                    st.column_config.TextColumn(
                        "Novedad / Observación"
                    )
                )
            },
            key="editor_reporte",
        )

        if diagnostico_pdf is not None:
            with st.expander(
                "🔎 Diagnóstico de lectura del PDF"
            ):
                st.write(
                    "Páginas con texto:",
                    diagnostico_pdf[
                        "paginas_con_texto"
                    ],
                )
                st.write(
                    "Tablas detectadas:",
                    diagnostico_pdf[
                        "cantidad_tablas"
                    ],
                )
                st.write(
                    "Tablas con columna de nombres:",
                    diagnostico_pdf[
                        "tablas_con_nombres"
                    ],
                )

                muestra = diagnostico_pdf[
                    "muestra"
                ]

                if not muestra.empty:
                    st.dataframe(
                        muestra,
                        hide_index=True,
                        use_container_width=True,
                    )
                else:
                    st.write(
                        "No se extrajeron filas de tablas."
                    )

        csv_data = df_editado.to_csv(
            index=False
        ).encode("utf-8-sig")

        st.download_button(
            label=(
                "📥 Descargar reporte ordenado (CSV)"
            ),
            data=csv_data,
            file_name=(
                "reporte_servicios_ordenado.csv"
            ),
            mime="text/csv",
        )

    except Exception as error:
        st.error(
            "No se pudo generar el reporte. "
            f"Detalle técnico: {error}"
        )
