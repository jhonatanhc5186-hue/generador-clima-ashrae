import streamlit as st
import requests
import os
from weasyprint import HTML

st.set_page_config(page_title="Generador de Reportes Climáticos", layout="wide")
st.title("🌍 Generador de Reportes: Condiciones Climáticas de Diseño")

# --- FUNCIONES DE LIMPIEZA ---
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
    "Seleccione el método de generación:", 
    ["📍 Búsqueda por Coordenadas (Data Satelital Histórica)", "🏢 Estación Local (Archivos EPW)"], 
    horizontal=True
)
st.markdown("---")

col1, col2, col3 = st.columns(3)
file_map = get_epw_mapping()

if "Coordenadas" in modo:
    usar_local = False
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
        # MODO SATELITAL (PROCESO INVISIBLE)
        # =========================================================
        with st.spinner("Procesando matriz de datos climáticos y renderizando formato PDF..."):
            
            # Enlace de procesamiento interno
            api_url = f"https://power.larc.nasa.gov/api/application/indicators/point?start={start_y}&end={end_y}&latitude={lat}&longitude={lon}&format=html&user=DAVE"
            
            try:
                respuesta = requests.get(api_url, timeout=30)
                if respuesta.status_code == 200:
                    html_crudo = respuesta.text
                    
                    # CSS AGRESIVO PARA FORZAR QUE LA TABLA ENCAJE EN A4 VERTICAL SIN CORTES
                    css_inyeccion = """
                    <style>
                        @page { 
                            size: A4 portrait; 
                            margin: 4mm; 
                        }
                        body { 
                            font-family: 'Times New Roman', serif; 
                            margin: 0; 
                            padding: 0; 
                            background-color: #ffffff;
                        }
                        table { 
                            width: 100% !important; 
                            max-width: 100% !important; 
                            table-layout: fixed !important; 
                            border-collapse: collapse !important; 
                            margin-bottom: 3px !important;
                        }
                        th, td { 
                            border: 1px solid black !important; 
                            padding: 1px 0.5px !important; 
                            text-align: center !important; 
                            font-size: 4.8px !important; /* Letra lo suficientemente pequeña para que entren todas las columnas */
                            line-height: 1 !important; 
                            word-wrap: break-word !important;
                            word-break: break-all !important;
                            overflow: hidden !important;
                        }
                        th { background-color: #0000cc !important; color: white !important; font-size: 5px !important; }
                        .title-bar, h1, h2, h3, h4, div { 
                            font-size: 7px !important; 
                        }
                    </style>
                    """
                    
                    # Reemplazar la cabecera original con nuestro CSS forzado
                    html_final = html_crudo.replace("</head>", f"{css_inyeccion}</head>")
                    
                    # Renderizar PDF a partir del HTML en memoria
                    pdf_file = HTML(string=html_final).write_pdf()
                    
                    st.success("¡Reporte generado exitosamente!")
                    
                    # Botón de descarga directa, sin vista previa
                    st.download_button(
                        label="📥 Descargar Reporte (PDF Vertical)", 
                        data=pdf_file, 
                        file_name=f"Condiciones_Climaticas_{lat}_{lon}.pdf", 
                        mime="application/pdf"
                    )
                else:
                    st.error("No se pudo obtener la información para las coordenadas especificadas.")
            except Exception as e:
                st.error("Error al procesar la matriz de datos.")

    else:
        # =========================================================
        # MODO EPW LOCAL
        # =========================================================
        with st.spinner("Procesando archivo EPW local..."):
            st.info("Función EPW en proceso. Generando tabla estructurada...")
            html_clon = "<html><body><h1>Reporte Local EPW</h1><p>Procesando data térmica.</p></body></html>"
            pdf_file = HTML(string=html_clon).write_pdf()
            st.download_button("📥 Descargar Reporte (PDF)", data=pdf_file, file_name=f"Reporte_{selected_city}.pdf", mime="application/pdf")
