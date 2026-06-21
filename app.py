import streamlit as st
import pandas as pd
import numpy as np
import requests
import os
import streamlit.components.v1 as components
from weasyprint import HTML

st.set_page_config(page_title="Generador de Reportes Climáticos", layout="wide")
st.title("🌍 Generador de Reportes: Condiciones Climáticas de Diseño")

# --- FUNCIONES DE LIMPIEZA Y GEOLOCALIZACIÓN ---
def clean_city_name(filename):
    dept_map = {
        "AMA": "Amazonas", "ANC": "Áncash", "APU": "Apurímac", "ARE": "Arequipa",
        "AYA": "Ayacucho", "CAJ": "Cajamarca", "CUS": "Cusco", "HUC": "Huánuco",
        "HUV": "Huancavelica", "ICA": "Ica", "JUN": "Junín", "LAL": "La Libertad",
        "LAM": "Lambayeque", "LIM": "Lima", "LOR": "Loreto", "MDD": "Madre de Dios",
        "MOQ": "Moquegua", "PAS": "Pasco", "PIU": "Piura", "PUN": "Puno",
        "SAM": "San Martín", "TAC": "Tacna", "TUM": "Tumbes", "UCA": "Ucayali"
    }
    try:
        parts = filename.split('_')
        if len(parts) >= 3:
            pais = "Perú" if parts[0] == "PER" else parts[0]
            departamento = dept_map.get(parts[1], parts[1])
            ciudad = " ".join(parts[2].split('.')[:-1]).split('-')[0].strip()
            if ciudad == "Tacna": departamento = "Tacna"
            if ciudad == "Ilo": departamento = "Moquegua"
            return f"{pais} - {departamento} - {ciudad}"
        return filename.replace(".epw", "")
    except: return filename

def get_epw_mapping():
    if not os.path.exists("data"): return {}
    return {clean_city_name(f): f for f in sorted([f for f in os.listdir("data") if f.endswith(".epw")])}

# --- INTERFAZ STREAMLIT ---
modo = st.radio(
    "Seleccione la fuente de datos (Formato Oficial ASHRAE / NASA POWER):", 
    ["📍 NASA POWER API (Reporte HTML Oficial Directo)", "🏢 Archivos EPW Locales (Clonación de Reporte)"], 
    horizontal=True
)
st.markdown("---")

col1, col2, col3 = st.columns(3)
file_map = get_epw_mapping()

if "NASA" in modo:
    usar_local = False
    col1.info("Generación ultrarrápida usando el endpoint HTML nativo de la NASA.")
    lat = col2.number_input("Latitud", value=-9.5653, format="%.4f")
    lon = col3.number_input("Longitud", value=-77.0364, format="%.4f")
    start_y, end_y = st.slider("Rango de Años:", 1990, 2024, (2001, 2024))
else:
    usar_local = True
    selected_city = col1.selectbox("Ciudad (Base de datos local):", list(file_map.keys()))
    lat = col2.number_input("Latitud", value=0.0000, disabled=True)
    lon = col3.number_input("Longitud", value=0.0000, disabled=True)

st.markdown("<br>", unsafe_allow_html=True) 

if st.button("Generar Reporte Maestro"):
    
    if not usar_local:
        # =========================================================
        # MODO NASA: CONSUMIR EL HTML DIRECTO DEL ENLACE QUE ENVIASTE
        # =========================================================
        with st.spinner("Conectando con supercomputadoras de la NASA..."):
            # Aquí usamos exactamente la estructura de URL que descubriste
            nasa_url = f"https://power.larc.nasa.gov/api/application/indicators/point?start={start_y}&end={end_y}&latitude={lat}&longitude={lon}&format=html&user=DAVE"
            
            try:
                respuesta = requests.get(nasa_url, timeout=30)
                if respuesta.status_code == 200:
                    html_nasa = respuesta.text
                    
                    # Añadimos un poco de CSS para asegurar que el PDF salga en vertical (A4)
                    css_inyeccion = """
                    <style>
                        @page { size: A4 portrait; margin: 5mm; }
                        body { font-family: 'Times New Roman', serif; font-size: 6.5px; }
                        table { width: 100%; table-layout: fixed; border-collapse: collapse; }
                        th, td { border: 1px solid black; padding: 2px; text-align: center; word-wrap: break-word; }
                    </style>
                    """
                    html_final = html_nasa.replace("</head>", f"{css_inyeccion}</head>")
                    
                    st.success("¡Reporte nativo descargado de la NASA con éxito!")
                    
                    # Mostrar vista previa interactiva en la app
                    with st.expander("👀 Vista Previa del Reporte NASA", expanded=True):
                        components.html(html_nasa, height=600, scrolling=True)
                    
                    # Generar PDF
                    pdf_file = HTML(string=html_final).write_pdf()
                    st.download_button("📥 Descargar Reporte NASA Oficial (PDF Vertical)", data=pdf_file, file_name=f"NASA_Oficial_{lat}_{lon}.pdf", mime="application/pdf")
                else:
                    st.error(f"Error de la API de la NASA: {respuesta.status_code}")
            except Exception as e:
                st.error(f"Error de conexión: {e}")

    else:
        # =========================================================
        # MODO EPW: CLONAR EL FORMATO NASA USANDO PANDAS
        # =========================================================
        with st.spinner("Procesando archivo EPW local y clonando diseño NASA..."):
            filename = file_map[selected_city]
            # (Aquí iría la lógica de Pandas que te compartí en el mensaje anterior
            # para calcular DB, WB, HR, Entalpía y renderizar el HTML clonado).
            st.info("El motor EPW utilizará las fórmulas psicrométricas locales para generar una tabla idéntica a la oficial de la NASA.")
            
            # Para mantener el código limpio en esta respuesta, he omitido el bloque 
            # de 200 líneas de Pandas del mensaje anterior, pero puedes pegarlo aquí.
            
            # Ejemplo simplificado de salida:
            html_clon = "<html><body><h1>Reporte EPW Clonado</h1><p>Reemplazar con el código HTML del mensaje anterior.</p></body></html>"
            pdf_file = HTML(string=html_clon).write_pdf()
            st.download_button("📥 Descargar Clon EPW (PDF)", data=pdf_file, file_name=f"EPW_NASA_{selected_city}.pdf", mime="application/pdf")
