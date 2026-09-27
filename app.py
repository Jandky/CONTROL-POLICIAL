import io
import re
import unicodedata

import pandas as pd
import pypdf
import streamlit as st


st.set_page_config(
    page_title="Control Policial de Servicios",
    page_icon="👮",
    layout="wide",
)


COLUMNAS_FINALES = [
    "Grado",
    "Nombre",
    "Identificación",
    "Servicio",
    "Horas",
    "Novedad / Observación",
]


ESTADOS_REVISION = {
    "REVISAR ORDEN",
    "REVISAR SERVICIO",
    "REVISAR HORA",
    "VARIAS ASIGNACIONES",
}


st.title("👮 Control Policial de Servicios")
st.write(
    "Verificación del personal del Excel contra los nombres "
    "encontrados en la orden PDF."
)
st.caption(
    "El sistema conserva únicamente las personas del listado base "
    "y no agrega personal externo."
)
st.markdown("---")


def texto_limpio(valor):
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass

    return " ".join(str(valor).replace("\n", " ").split()).strip()


def normalizar(valor):
    texto = texto_limpio(valor).upper()

    texto = unicodedata.normalize("NFKD", texto)

    texto = "".join(
        caracter
        for caracter in texto
        if not unicodedata.combining(caracter)
    )

    return " ".join(texto.split())


def buscar_columna(columnas, opciones):
    for columna in columnas:
        columna_normalizada = normalizar(columna)

        if any(
            opcion in columna_normalizada
            for opcion in opciones
        ):
            return columna

    return None


def leer_archivo_tabular(archivo):
    nombre_archivo = archivo.name.lower()

    archivo.seek(0)

    if nombre_archivo.endswith(".csv"):
        contenido = archivo.getvalue()
        ultimo_error = None

        for codificacion in (
            "utf-8-sig",
            "cp1252",
            "latin-1",
        ):
            try:
                return pd.read_csv(
                    io.BytesIO(contenido),
                    encoding=codificacion,
                    sep=None,
                    engine="python",
                    dtype=str,
                    keep_default_na=False,
                )

            except (
                UnicodeDecodeError,
                pd.errors.ParserError,
            ) as error:
                ultimo_error = error

        raise ValueError(
            "No fue posible leer el CSV. "
            f"Detalle: {ultimo_error}"
        )

    return pd.read_excel(
        archivo,
        dtype=str,
        keep_default_na=False,
    )


def preparar_listado_base(df_base):
    if df_base.empty:
        raise ValueError(
            "El listado base está vacío."
        )

    columnas = list(df_base.columns)

    columna_nombre = buscar_columna(
        columnas,
        (
            "NOMBRE",
            "APELLIDO",
            "FUNCIONARIO",
            "PERSONAL",
        ),
    )

    columna_grado = buscar_columna(
        columnas,
        (
            "GRADO",
            "JERARQUIA",
            "RANGO",
        ),
    )

    columna_identificacion = buscar_columna(
        columnas,
        (
            "IDENTIFICACION",
            "IDENTIFICACIÓN",
            "CEDULA",
            "CÉDULA",
            "DOCUMENTO",
            "PLACA",
            "NIP",
        ),
    )

    if columna_nombre is None:
        raise ValueError(
            "No encontré la columna de nombres. "
            "El Excel debe tener una columna llamada "
            "'Nombre', 'Apellidos' o 'Funcionario'."
        )

    resultado = pd.DataFrame()

    if columna_grado is not None:
        resultado["Grado"] = (
            df_base[columna_grado]
            .map(texto_limpio)
            .replace("", "-")
        )
    else:
        resultado["Grado"] = "-"

    resultado["Nombre"] = (
        df_base[columna_nombre]
        .map(texto_limpio)
        .str.upper()
    )

    if columna_identificacion is not None:
        resultado["Identificación"] = (
            df_base[columna_identificacion]
            .map(texto_limpio)
            .replace("", "-")
        )
    else:
        resultado["Identificación"] = "-"

    resultado = resultado[
        resultado["Nombre"].map(normalizar).ne("")
    ].copy()

    if resultado.empty:
        raise ValueError(
            "No se encontraron nombres válidos "
            "en el listado base."
        )

    resultado["Nombre_clave"] = (
        resultado["Nombre"].map(normalizar)
    )

    return resultado.reset_index(drop=True)


def extraer_texto_pdf(archivo):
    archivo.seek(0)

    lector = pypdf.PdfReader(archivo)

    paginas = []
    cantidad_paginas_con_texto = 0

    for numero_pagina, pagina in enumerate(
        lector.pages,
        start=1,
    ):
        texto = pagina.extract_text() or ""

        if texto.strip():
            cantidad_paginas_con_texto += 1

        paginas.append(
            f"\n===== PAGINA {numero_pagina} =====\n"
            f"{texto}"
        )

    return "\n".join(paginas), cantidad_paginas_con_texto


def construir_lineas(texto):
    lineas = []

    for linea in texto.splitlines():
        linea = texto_limpio(linea)

        if not linea:
            continue

        if linea.upper().startswith("===== PAGINA"):
            continue

        if re.match(
            r"^1DH[- ]FR[- ]0131",
            linea,
            flags=re.IGNORECASE,
        ):
            continue

        if re.match(
            r"^1DS[- ]OS[- ]0001",
            linea,
            flags=re.IGNORECASE,
        ):
            continue

        if re.match(
            r"^PAGINA?\s+\d+",
            linea,
            flags=re.IGNORECASE,
        ):
            continue

        if re.match(
            r"^Página\s+\d+\s+de\s+\d+",
            linea,
            flags=re.IGNORECASE,
        ):
            continue

        lineas.append(linea)

    return lineas


def es_linea_hora(linea):
    linea_normalizada = normalizar(linea)

    patrones = [
        r"\bDESDE\b.*\bHORA",
        r"\bDE\s+\d{1,2}:\d{2}\s+A\s+\d{1,2}:\d{2}",
        r"\b\d{1,2}:\d{2}\s+A\s+\d{1,2}:\d{2}",
        r"\b\d{1,2}:\d{2}\s+HORAS?",
        r"\bHASTA\s+LAS?\b",
    ]

    return any(
        re.search(
            patron,
            linea_normalizada,
            flags=re.IGNORECASE,
        )
        for patron in patrones
    )


def limpiar_hora(linea):
    hora = texto_limpio(linea)

    hora = re.sub(
        r"\s+",
        " ",
        hora,
    )

    return hora


def es_linea_no_util(linea):
    linea_normalizada = normalizar(linea)

    palabras_ignoradas = [
        "GRADO",
        "APELLIDOS Y NOMBRES",
        "NOMBRES Y APELLIDOS",
        "CEDULA",
        "CÉDULA",
        "IDENTIFICACION",
        "IDENTIFICACIÓN",
        "TELEFONO",
        "TELÉFONO",
        "CELULAR",
        "ROL",
        "NO APLICA",
        "NRO",
        "PAGINA",
        "APROBACION",
        "APROBACIÓN",
        "VERSION",
        "VERSIÓN",
        "MINISTERIO DE DEFENSA",
        "POLICIA NACIONAL",
        "POLICÍA NACIONAL",
        "ESCUELA DE SUBOFICIALES",
        "PROYECTO ORDEN DEL DIA",
        "PROYECTO ORDEN DEL DÍA",
        "SERVICIOS DE AGRUPACION POLICIAL",
        "SERVICIOS DE AGRUPACIÓN POLICIAL",
        "SERVICIOS DE SUPERVISION",
        "SERVICIOS DE SUPERVISIÓN",
        "SERVICIOS DE ESTUDIANTES FISCAL",
        "COMPANIA:",
        "COMPAÑÍA:",
        "COMPAÑIA:",
    ]

    return any(
        palabra in linea_normalizada
        for palabra in palabras_ignoradas
    )


def parece_identificacion(linea):
    linea_limpia = linea.replace(".", "").strip()

    return bool(
        re.fullmatch(
            r"\d{5,14}",
            linea_limpia,
        )
    )


def parece_grado(linea):
    linea_normalizada = normalizar(linea)

    grados = {
        "IT",
        "IJ",
        "SI",
        "SC",
        "PT",
        "CM",
        "MY",
        "TE",
        "ST",
        "CT",
        "SV",
        "SUBTENIENTE",
        "TENIENTE",
        "CAPITAN",
        "CAPITÁN",
        "MAYOR",
        "CORONEL",
        "INTENDENTE",
    }

    return linea_normalizada in grados


def es_encabezado_servicio(lineas, indice):
    """
    Detecta los títulos que aparecen antes de:
    Desde las HH:MM horas...
    GR
    APELLIDOS Y NOMBRES
    NOMBRE
    CÉDULA
    """
    linea_actual = normalizar(lineas[indice])

    if es_linea_hora(linea_actual):
        return False

    if parece_grado(linea_actual):
        return False

    if parece_identificacion(linea_actual):
        return False

    if es_linea_no_util(linea_actual):
        return False

    if len(linea_actual) < 4:
        return False

    palabras_excluidas = [
        "FORMACION",
        "FORMACIÓN",
        "INICIO DEL SERVICIO",
        "CON TODOS LOS ELEMENTOS",
        "UNIFORME",
        "ARMAMENTO",
        "CHAQUETA",
        "CHALECO",
        "PITO",
        "TONFA",
        "LINTERNA",
        "RADIO DE COMUNICACIÓN",
        "ELEMENTOS PARA LA PRESTACION",
        "ELEMENTOS PARA LA PRESTACIÓN",
        "TODO EL PERSONAL",
        "DEBERA FORMAR",
        "DEBERÁ FORMAR",
        "HORAS",
        "ACTIVIDAD A DESARROLLAR",
        "RESPONSABILIDAD",
        "VIGENCIA",
        "FINALIDAD DEL SERVICIO",
        "INSTRUCCIONES GENERALES",
        "DESPLAZAMIENTO",
        "LUGAR DEL SERVICIO",
        "FECHA Y HORA",
    ]

    if any(
        palabra in linea_actual
        for palabra in palabras_excluidas
    ):
        return False

    # Si en las siguientes líneas aparece un rango de hora,
    # se considera el título del servicio.
    for siguiente in lineas[
        indice + 1:min(len(lineas), indice + 8)
    ]:
        if es_linea_hora(siguiente):
            return True

        if (
            parece_grado(siguiente)
            or parece_identificacion(siguiente)
        ):
            break

    return False


def nombre_coincide(nombre_base, linea):
    """
    Coincidencia estricta del nombre completo.
    Se permiten textos adicionales como '(CONDUCTOR)'.
    """
    nombre = normalizar(nombre_base)
    contenido = normalizar(linea)

    if not nombre or not contenido:
        return False

    patron = rf"(?<!\w){re.escape(nombre)}(?!\w)"

    return re.search(patron, contenido) is not None


def extraer_asignaciones_pdf(
    archivo,
    nombres_base,
):
    """
    Lee la orden PDF como bloques:
    servicio -> hora -> nombres siguientes.

    Devuelve únicamente coincidencias exactas con el Excel.
    """
    texto, paginas_con_texto = extraer_texto_pdf(
        archivo
    )

    lineas = construir_lineas(texto)

    nombres_normalizados = {
        normalizar(nombre): nombre
        for nombre in nombres_base
    }

    asignaciones = {
        nombre: []
        for nombre in nombres_normalizados
    }

    bloques_diagnostico = []

    servicio_actual = None
    hora_actual = None

    indice = 0

    while indice < len(lineas):
        linea = lineas[indice]

        if es_encabezado_servicio(
            lineas,
            indice,
        ):
            servicio_actual = linea
            hora_actual = None

        elif es_linea_hora(linea):
            hora_actual = limpiar_hora(linea)

        else:
            coincidencias = [
                nombre
                for nombre in nombres_normalizados
                if nombre_coincide(
                    nombre,
                    linea,
                )
            ]

            if (
                len(coincidencias) == 1
                and servicio_actual
                and hora_actual
            ):
                nombre_encontrado = coincidencias[0]

                asignaciones[
                    nombre_encontrado
                ].append(
                    (
                        servicio_actual,
                        hora_actual,
                    )
                )

                bloques_diagnostico.append(
                    {
                        "Nombre": nombres_normalizados[
                            nombre_encontrado
                        ],
                        "Servicio": servicio_actual,
                        "Horas": hora_actual,
                        "Línea PDF": linea,
                    }
                )

        indice += 1

    diagnostico = {
        "paginas_con_texto": paginas_con_texto,
        "lineas_extraidas": len(lineas),
        "coincidencias": pd.DataFrame(
            bloques_diagnostico
        ),
    }

    return asignaciones, diagnostico


def procesar_orden_excel_csv(df_orden):
    """
    Procesa una orden Excel/CSV que sí tenga columnas
    separadas de nombre, servicio y hora.
    """
    if df_orden.empty:
        raise ValueError(
            "La orden Excel/CSV está vacía."
        )

    columnas = list(df_orden.columns)

    columna_nombre = buscar_columna(
        columnas,
        (
            "NOMBRE",
            "APELLIDO",
            "FUNCIONARIO",
        ),
    )

    columna_servicio = buscar_columna(
        columnas,
        (
            "SERVICIO",
            "PUESTO",
            "CARGO",
            "ROL",
        ),
    )

    columna_hora = buscar_columna(
        columnas,
        (
            "HORA",
            "HORARIO",
            "TURNO",
        ),
    )

    if columna_nombre is None:
        raise ValueError(
            "La orden debe tener una columna de nombres."
        )

    resultado = {}

    for _, fila in df_orden.iterrows():
        nombre = normalizar(
            fila[columna_nombre]
        )

        if not nombre:
            continue

        servicio = (
            texto_limpio(fila[columna_servicio])
            if columna_servicio is not None
            else ""
        )

        hora = (
            texto_limpio(fila[columna_hora])
            if columna_hora is not None
            else ""
        )

        resultado.setdefault(
            nombre,
            [],
        ).append(
            (
                servicio,
                hora,
            )
        )

    return resultado


def construir_reporte(
    df_base,
    asignaciones,
):
    resultado = df_base.copy()

    servicios = []
    horas = []

    for nombre_clave in resultado["Nombre_clave"]:
        registros = list(
            dict.fromkeys(
                asignaciones.get(
                    nombre_clave,
                    [],
                )
            )
        )

        if len(registros) == 0:
            servicios.append("REVISAR ORDEN")
            horas.append("REVISAR ORDEN")

        elif len(registros) > 1:
            servicios.append("VARIAS ASIGNACIONES")
            horas.append(
                " | ".join(
                    sorted(
                        set(
                            hora
                            for _, hora in registros
                            if hora
                        )
                    )
                )
                or "REVISAR HORA"
            )

        else:
            servicio, hora = registros[0]

            servicios.append(
                servicio
                if servicio
                else "REVISAR SERVICIO"
            )

            horas.append(
                hora
                if hora
                else "REVISAR HORA"
            )

    resultado["Servicio"] = servicios
    resultado["Horas"] = horas
    resultado["Novedad / Observación"] = ""

    return resultado[COLUMNAS_FINALES]


def crear_excel(df):
    salida = io.BytesIO()

    with pd.ExcelWriter(
        salida,
        engine="openpyxl",
    ) as writer:
        df.to_excel(
            writer,
            index=False,
            sheet_name="Reporte",
        )

    salida.seek(0)

    return salida.getvalue()


columna_izquierda, columna_derecha = st.columns(2)

with columna_izquierda:
    st.subheader("1. Listado base")

    archivo_base = st.file_uploader(
        "Sube el Excel o CSV del personal",
        type=[
            "xlsx",
            "xls",
            "csv",
        ],
        key="archivo_base",
    )

with columna_derecha:
    st.subheader("2. Orden o documento")

    archivo_orden = st.file_uploader(
        "Sube el PDF, Excel o CSV de la orden",
        type=[
            "pdf",
            "xlsx",
            "xls",
            "csv",
        ],
        key="archivo_orden",
    )


if archivo_base is None or archivo_orden is None:
    st.info(
        "Carga los dos archivos para iniciar la "
        "verificación."
    )

else:
    try:
        df_base_original = leer_archivo_tabular(
            archivo_base
        )

        df_base = preparar_listado_base(
            df_base_original
        )

        nombre_orden = archivo_orden.name.lower()

        if nombre_orden.endswith(".pdf"):
            asignaciones, diagnostico = (
                extraer_asignaciones_pdf(
                    archivo_orden,
                    set(df_base["Nombre_clave"]),
                )
            )

            if diagnostico["paginas_con_texto"] == 0:
                st.error(
                    "El PDF no contiene texto extraíble. "
                    "Parece ser un documento escaneado y "
                    "requiere OCR."
                )

            elif diagnostico["coincidencias"].empty:
                st.warning(
                    "Se pudo leer el PDF, pero no se "
                    "encontraron coincidencias exactas "
                    "entre el Excel y la orden."
                )

        else:
            df_orden = leer_archivo_tabular(
                archivo_orden
            )

            asignaciones = procesar_orden_excel_csv(
                df_orden
            )

            diagnostico = None

        df_resultado = construir_reporte(
            df_base,
            asignaciones,
        )

        st.markdown("---")
        st.subheader("📊 Métricas")

        asignados = (
            ~df_resultado["Servicio"].isin(
                ESTADOS_REVISION
            )
        ).sum()

        pendientes = (
            df_resultado["Servicio"].isin(
                ESTADOS_REVISION
            )
        ).sum()

        total = len(df_resultado)

        m1, m2, m3 = st.columns(3)

        m1.metric(
            "Personal del Excel",
            total,
        )

        m2.metric(
            "Asignaciones encontradas",
            int(asignados),
        )

        m3.metric(
            "Pendientes de revisión",
            int(pendientes),
        )

        st.markdown("---")
        st.subheader("📝 Reporte verificado")

        st.info(
            "Solo se muestran personas del Excel. "
            "Si aparece 'REVISAR ORDEN', significa que "
            "el nombre no fue encontrado con un servicio "
            "y una hora confiables."
        )

        df_editado = st.data_editor(
            df_resultado,
            hide_index=True,
            num_rows="fixed",
            use_container_width=True,
            column_config={
                "Novedad / Observación": (
                    st.column_config.TextColumn(
                        "Novedad / Observación"
                    )
                )
            },
            key="editor_reporte",
        )

        st.markdown("---")
        st.subheader("📥 Descargar reporte")

        csv_data = df_editado.to_csv(
            index=False
        ).encode("utf-8-sig")

        excel_data = crear_excel(
            df_editado
        )

        descarga_csv, descarga_excel = st.columns(2)

        with descarga_csv:
            st.download_button(
                label="Descargar CSV",
                data=csv_data,
                file_name=(
                    "reporte_servicios_verificado.csv"
                ),
                mime="text/csv",
            )

        with descarga_excel:
            st.download_button(
                label="Descargar Excel",
                data=excel_data,
                file_name=(
                    "reporte_servicios_verificado.xlsx"
                ),
                mime=(
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                ),
            )

        if diagnostico is not None:
            st.markdown("---")

            with st.expander(
                "🔎 Ver diagnóstico de lectura del PDF"
            ):
                st.write(
                    "Páginas con texto:",
                    diagnostico[
                        "paginas_con_texto"
                    ],
                )

                st.write(
                    "Líneas extraídas:",
                    diagnostico[
                        "lineas_extraidas"
                    ],
                )

                coincidencias = diagnostico[
                    "coincidencias"
                ]

                if not coincidencias.empty:
                    st.dataframe(
                        coincidencias,
                        hide_index=True,
                        use_container_width=True,
                    )
                else:
                    st.warning(
                        "No hubo coincidencias para "
                        "mostrar."
                    )

    except Exception as error:
        st.error(
            "Ocurrió un error al procesar los archivos."
        )

        st.exception(error)
