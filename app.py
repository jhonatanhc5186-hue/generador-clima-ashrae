import streamlit as st
import pandas as pd
import numpy as np
import requests
import os
import re
import streamlit.components.v1 as components
from weasyprint import HTML

st.set_page_config(page_title="Generador de Reportes Climáticos", layout="wide")
st.title("🌍 Generador de Reportes: Condiciones Climáticas de Diseño")

# --- 1. FUNCIONES BASE ---
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

def format_coord(val, is_lat):
    try: return f"{abs(float(val)):.4f}{'N' if float(val) >= 0 else 'S'}" if is_lat else f"{abs(float(val)):.4f}{'E' if float(val) >= 0 else 'W'}"
    except: return str(val)

# --- TERMODINÁMICA ---
def calc_wb(T, RH):
    return T * np.arctan(0.151977 * (RH + 8.313659)**0.5) + np.arctan(T + RH) - np.arctan(RH - 1.676331) + 0.00391838 * (RH)**1.5 * np.arctan(0.023101 * RH) - 4.686035

def calc_enthalpy(T, HR):
    return 1.006 * T + (HR/1000) * (2501 + 1.86 * T)

def mc(sub, base_col, target_col, t):
    h = sub[(sub[base_col] >= t - 0.2) & (sub[base_col] <= t + 0.2)]
    return h[target_col].mean() if not h.empty else sub[target_col].mean()

# --- 2. INTERFAZ ---
modo = st.radio(
    "Seleccione la fuente de datos:", 
    ["📍 Búsqueda por Coordenadas (Data Histórica Global)", "🏢 Estación Local (Archivos EPW)"], 
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

# --- ESTILOS CSS UNIFICADOS (PDF y VISTA PREVIA) ---
css_pdf = """
<style>
    @page { size: A4 portrait; margin: 4mm; }
    body { font-family: 'Times New Roman', serif; margin: 0; padding: 0; background-color: #ffffff; }
    table { width: 100% !important; max-width: 100% !important; table-layout: fixed !important; border-collapse: collapse !important; margin-bottom: 3px !important; }
    th, td { border: 1px solid black !important; padding: 1.5px !important; text-align: center !important; font-size: 5.2px !important; line-height: 1 !important; word-wrap: break-word !important; word-break: break-all !important; overflow: hidden !important; }
    th, .header-blue { background-color: #0000cc !important; color: white !important; font-size: 6px !important; font-weight: bold; }
    .gray-header { background-color: #e6e6e6 !important; font-weight: bold; }
    .title-bar, h1, h2, h3, h4, div { font-size: 9px !important; text-align: center; font-weight: bold; margin-bottom: 4px; color: #000; }
    a { display: none !important; } 
</style>
"""

css_preview = """
<style>
    body { font-family: 'Times New Roman', serif; font-size: 10px; background-color: #f9f9f9; padding: 10px; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 10px; table-layout: fixed; background-color: #fff; border: 1px solid #000; }
    th, td { border: 1px solid #000; padding: 4px; text-align: center; word-wrap: break-word; font-size: 11px; }
    th, .header-blue { background-color: #0000cc; color: white; font-weight: bold; font-size: 12px; }
    .gray-header { background-color: #e6e6e6; font-weight: bold; }
    .title-bar { font-size: 16px; font-weight: bold; text-align: center; margin-bottom: 10px; color: #000; }
    a { display: none !important; }
</style>
"""

if st.button("Generar Reporte Maestro"):
    
    if not usar_local:
        # =========================================================
        # MODO COORDENADAS: EXTRACCIÓN HTML Y LIMPIEZA
        # =========================================================
        with st.spinner("Procesando matriz de datos climáticos globales..."):
            api_url = f"https://power.larc.nasa.gov/api/application/indicators/point?start={start_y}&end={end_y}&latitude={lat}&longitude={lon}&format=html&user=DAVE"
            try:
                respuesta = requests.get(api_url, timeout=30)
                if respuesta.status_code == 200:
                    html_crudo = respuesta.text
                    
                    # Limpieza de Privacidad (Ocultar origen)
                    html_limpio = re.sub(r'(?i)https?://power\.larc\.nasa\.gov[^\s<]*', '', html_crudo)
                    html_limpio = re.sub(r'POWER Climatic Design Conditions \(.*?\)', 'CONDICIONES CLIMÁTICAS DE DISEÑO', html_limpio)
                    html_limpio = html_limpio.replace("POWER Climatic Design Conditions", "CONDICIONES CLIMÁTICAS DE DISEÑO")
                    
                    html_preview_final = html_limpio.replace("</head>", f"{css_preview}</head>")
                    html_pdf_final = html_limpio.replace("</head>", f"{css_pdf}</head>")
                    
                    st.success("¡Matriz procesada exitosamente!")
                    
                    with st.expander("👀 Vista Previa del Reporte de Diseño", expanded=True):
                        components.html(html_preview_final, height=600, scrolling=True)
                    
                    pdf_file = HTML(string=html_pdf_final).write_pdf()
                    st.download_button(label="📥 Descargar Reporte (PDF Vertical)", data=pdf_file, file_name=f"Condiciones_Climaticas_{lat}_{lon}.pdf", mime="application/pdf")
                else: st.error("Error al obtener información satelital.")
            except: st.error("Error de conexión durante el procesamiento.")

    else:
        # =========================================================
        # MODO EPW LOCAL: CLONACIÓN MATEMÁTICA Y VISUAL
        # =========================================================
        with st.spinner("Procesando archivo EPW local y clonando estructura de diseño..."):
            filename = file_map[selected_city]
            period_display = "TMYx"
            try:
                for p in filename.replace(".epw", "").split('.'):
                    if "-" in p and len(p) == 9 and p.split('-')[0].isdigit(): period_display = p
                with open(f"data/{filename}", 'r', encoding='utf-8') as f:
                    h_data = f.readline().split(',')
                    lat_val, lon_val, alt_display = float(h_data[6]), float(h_data[7]), float(h_data[9].strip())
            except: lat_val, lon_val, alt_display = 0, 0, 0

            # Extracción del archivo EPW
            df = pd.read_csv(f"data/{filename}", skiprows=8, header=None, usecols=[1,2,6,7,8,9,13,14,21,33], names=['Month','Day','DB','DP','RH','Press','RadAvg','RadClr','WS','Precip'])
            df['Press_kPa'] = df['Press'] / 1000
            df['Precip'] = pd.to_numeric(df['Precip'], errors='coerce').fillna(0).apply(lambda x: 0 if x > 900 else x)
            df['Year'] = 2024 # Base para TMY
            
            # Cálculos Termodinámicos y Psicrométricos
            df['Pv'] = 0.61078 * np.exp(17.27 * df['DP'] / (df['DP'] + 237.3))
            df['HR'] = 1000 * 0.62198 * df['Pv'] / (df['Press_kPa'] - df['Pv']) 
            df['Enth'] = calc_enthalpy(df['DB'], df['HR'])
            df['WB'] = calc_wb(df['DB'], df['RH'])

            stdp_display = f"{101.325 * (1 - 2.25577e-5 * alt_display)**5.25588:.2f}"
            db_max_ann, db_min_ann = df['DB'].quantile(0.996), df['DB'].quantile(0.004)
            wb_max_ann, dp_max_ann = df['WB'].quantile(0.996), df['DP'].quantile(0.996)
            enth_max_ann = df['Enth'].quantile(0.996)
            hottest_month = df.groupby('Month')['DB'].mean().idxmax()
            coldest_month = df.groupby('Month')['DB'].mean().idxmin()

            # --- CONSTRUCCIÓN DE TABLA TRANSPUESTA MENSUAL ---
            cols = [df] + [df[df['Month'] == m] for m in range(1, 13)]
            
            def build_row(title, rowspan, subtitle, sub2, func):
                vals = [func(c) if not c.empty else 0 for c in cols]
                row_html = f"<tr>"
                if title: row_html += f"<td rowspan='{rowspan}' class='gray-header'>{title}</td>"
                if subtitle: row_html += f"<td class='gray-header'>{subtitle}</td>"
                if sub2: row_html += f"<td class='gray-header'>{sub2}</td>"
                for v in vals: row_html += f"<td>{v:.1f}</td>" if isinstance(
