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

# --- TERMODINÁMICA PARA EPW ---
def calc_wb(T, RH):
    return T * np.arctan(0.151977 * (RH + 8.313659)**0.5) + np.arctan(T + RH) - np.arctan(RH - 1.676331) + 0.00391838 * (RH)**1.5 * np.arctan(0.023101 * RH) - 4.686035

def calc_enthalpy(T, HR):
    return 1.006 * T + (HR/1000) * (2501 + 1.86 * T)

def mc(sub, base_col, target_col, t):
    h = sub[(sub[base_col] >= t - 0.2) & (sub[base_col] <= t + 0.2)]
    return h[target_col].mean() if not h.empty else sub[target_col].mean()

# --- 2. INTERFAZ ---
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

# Estilos CSS compartidos (para Vista Previa web y PDF)
css_pdf = """
<style>
    @page { size: A4 portrait; margin: 4mm; }
    body { font-family: 'Times New Roman', serif; margin: 0; padding: 0; background-color: #ffffff; }
    table { width: 100% !important; max-width: 100% !important; table-layout: fixed !important; border-collapse: collapse !important; margin-bottom: 3px !important; }
    th, td { border: 1px solid black !important; padding: 1px 0.5px !important; text-align: center !important; font-size: 4.8px !important; line-height: 1 !important; word-wrap: break-word !important; word-break: break-all !important; overflow: hidden !important; }
    th { background-color: #0000cc !important; color: white !important; font-size: 5px !important; }
    .title-bar, h1, h2, h3, h4, div { font-size: 7px !important; text-align: center; font-weight: bold; margin-bottom: 4px; }
    a { display: none !important; } /* Ocultar cualquier enlace residual */
</style>
"""

css_preview = """
<style>
    body { font-family: 'Times New Roman', serif; font-size: 10px; background-color: #f9f9f9; padding: 10px; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 10px; table-layout: fixed; background-color: #fff; }
    th, td { border: 1px solid #333; padding: 4px; text-align: center; word-wrap: break-word; }
    th { background-color: #0000cc; color: white; font-size: 11px; }
    .title-bar { font-size: 14px; font-weight: bold; text-align: center; margin-bottom: 10px; color: #000; }
    .gray-header { background-color: #e6e6e6; font-weight: bold; }
    a { display: none !important; }
</style>
"""

if st.button("Generar Reporte Maestro"):
    
    if not usar_local:
        with st.spinner("Procesando matriz de datos climáticos..."):
            api_url = f"https://power.larc.nasa.gov/api/application/indicators/point?start={start_y}&end={end_y}&latitude={lat}&longitude={lon}&format=html&user=DAVE"
            
            try:
                respuesta = requests.get(api_url, timeout=30)
                if respuesta.status_code == 200:
                    html_crudo = respuesta.text
                    
                    # --- FILTRO DE PRIVACIDAD: LIMPIEZA DE RASTROS ---
                    # 1. Eliminar URLs
                    html_limpio = re.sub(r'(?i)https?://power\.larc\.nasa\.gov[^\s<]*', '', html_crudo)
                    # 2. Reemplazar títulos originales para mayor privacidad
                    html_limpio = re.sub(r'POWER Climatic Design Conditions \(.*?\)', 'CONDICIONES CLIMÁTICAS DE DISEÑO', html_limpio)
                    html_limpio = html_limpio.replace("POWER Climatic Design Conditions", "CONDICIONES CLIMÁTICAS DE DISEÑO")
                    
                    # Ensamblar HTMLs
                    html_preview_final = html_limpio.replace("</head>", f"{css_preview}</head>")
                    html_pdf_final = html_limpio.replace("</head>", f"{css_pdf}</head>")
                    
                    st.success("¡Matriz procesada exitosamente!")
                    
                    # Vista Previa
                    with st.expander("👀 Vista Previa del Reporte", expanded=True):
                        components.html(html_preview_final, height=600, scrolling=True)
                    
                    # Renderizar y descargar PDF
                    pdf_file = HTML(string=html_pdf_final).write_pdf()
                    st.download_button(label="📥 Descargar Reporte (PDF Vertical)", data=pdf_file, file_name=f"Condiciones_Climaticas_{lat}_{lon}.pdf", mime="application/pdf")
                else:
                    st.error("Error al obtener información de la matriz satelital.")
            except Exception as e:
                st.error("Error de conexión durante el procesamiento.")

    else:
        with st.spinner("Procesando archivo EPW local y calculando matriz termodinámica..."):
            filename = file_map[selected_city]
            period_display = "TMYx"
            try:
                with open(f"data/{filename}", 'r', encoding='utf-8') as f:
                    h_data = f.readline().split(',')
                    lat_val, lon_val, alt_display = float(h_data[6]), float(h_data[7]), float(h_data[9].strip())
            except: lat_val, lon_val, alt_display = 0, 0, 0

            # Extracción de EPW
            df = pd.read_csv(f"data/{filename}", skiprows=8, header=None, usecols=[1,2,6,7,8,9,13,14,21,33], names=['Month','Day','DB','DP','RH','Press','RadAvg','RadClr','WS','Precip'])
            df['Press_kPa'] = df['Press'] / 1000
            df['Precip'] = pd.to_numeric(df['Precip'], errors='coerce').fillna(0).apply(lambda x: 0 if x > 900 else x)
            df['Year'] = 2024
            
            # Termodinámica
            df['Pv'] = 0.61078 * np.exp(17.27 * df['DP'] / (df['DP'] + 237.3))
            df['HR'] = 1000 * 0.62198 * df['Pv'] / (df['Press_kPa'] - df['Pv']) 
            df['Enth'] = calc_enthalpy(df['DB'], df['HR'])
            df['WB'] = calc_wb(df['DB'], df['RH'])

            years_count = 1
            stdp_display = f"{101.325 * (1 - 2.25577e-5 * alt_display)**5.25588:.2f}"

            # Construcción de la Tabla Mensual (Clonando formato Oficial)
            cols = [df] + [df[df['Month'] == m] for m in range(1, 13)]
            
            def build_row(title, rowspan, subtitle, sub2, func):
                vals = [func(c) if not c.empty else 0 for c in cols]
                row_html = f"<tr>"
                if title: row_html += f"<td rowspan='{rowspan}' style='font-weight:bold;'>{title}</td>"
                if subtitle: row_html += f"<td>{subtitle}</td>"
                if sub2: row_html += f"<td>{sub2}</td>"
                for v in vals: row_html += f"<td>{v:.1f}</td>" if isinstance(v, float) else f"<td>{v}</td>"
                row_html += "</tr>"
                return row_html

            m_rows = build_row("Temperatures,<br>Degree-Days", 6, "DBAvg", "", lambda x: x['DB'].mean())
            m_rows += build_row(None, 0, "DBStd", "", lambda x: x['DB'].std())
            m_rows += build_row(None, 0, "HDD10.0", "", lambda x: (10.0 - x['DB']).clip(lower=0).sum() / 24)
            m_rows += build_row(None, 0, "CDD10.0", "", lambda x: (x['DB'] - 10.0).clip(lower=0).sum() / 24)
            m_rows += build_row(None, 0, "CDH23.3", "", lambda x: (x['DB'] - 23.3).clip(lower=0).sum())
            m_rows += build_row(None, 0, "CDH26.7", "", lambda x: (x['DB'] - 26.7).clip(lower=0).sum())
            m_rows += build_row("Wind (m/s)", 1, "WSAvg", "", lambda x: x['WS'].mean())
            
            m_rows += build_row("Monthly Design<br>DB / MCWB", 4, "0.4%", "DB", lambda x: x['DB'].quantile(0.996))
            m_rows += build_row(None, 0, "", "MCWB", lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.996)))
            m_rows += build_row(None, 0, "2%", "DB", lambda x: x['DB'].quantile(0.980))
            m_rows += build_row(None, 0, "", "MCWB", lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.980)))

            # HTML Base
            html_base = f"""
            <html><head></head>
            <body>
                <div class="title-bar">CONDICIONES CLIMÁTICAS DE DISEÑO</div>
                <table style="border:none; border-top:1.5px solid #000; border-bottom:1.5px solid #000; margin-bottom:5px;">
                    <tr>
                        <td style="border:none; text-align:left;"><b>Latitude:</b> {format_coord(lat_val, True)}</td>
                        <td style="border:none; text-align:left;"><b>Longitude:</b> {format_coord(lon_val, False)}</td>
                        <td style="border:none; text-align:left;"><b>Elevation:</b> {alt_display}</td>
                        <td style="border:none; text-align:left;"><b>StdPres:</b> {stdp_display}</td>
                        <td style="border:none; text-align:left;"><b>Time Period:</b> {period_display}</td>
                    </tr>
                </table>

                <table>
                    <tr><th colspan="16" class="nasa-blue">Monthly Climatic Design Conditions</th></tr>
                    <tr class="gray-header">
                        <td colspan="3">Parameters</td>
                        <td>Annual</td><td>Jan</td><td>Feb</td><td>Mar</td><td>Apr</td><td>May</td><td>Jun</td>
                        <td>Jul</td><td>Aug</td><td>Sep</td><td>Oct</td><td>Nov</td><td>Dec</td>
                    </tr>
                    {m_rows}
                </table>
            </body></html>
            """
            
            # Ensamblar HTMLs con sus respectivos CSS
            html_preview_final = html_base.replace("</head>", f"{css_preview}</head>")
            html_pdf_final = html_base.replace("</head>", f"{css_pdf}</head>")
            
            st.success("¡Matriz procesada exitosamente!")
            
            # Vista Previa
            with st.expander("👀 Vista Previa del Reporte (Clon EPW)", expanded=True):
                components.html(html_preview_final, height=600, scrolling=True)
            
            # Descarga
            pdf_file = HTML(string=html_pdf_final).write_pdf()
            st.download_button(label="📥 Descargar Reporte (PDF Vertical)", data=pdf_file, file_name=f"Reporte_EPW_{selected_city}.pdf", mime="application/pdf")
