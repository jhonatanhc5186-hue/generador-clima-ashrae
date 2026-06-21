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

            m_rows += build_row("Monthly Design<br>WB / MCDB", 4, "0.4%", "WB", lambda x: x['WB'].quantile(0.996))
            m_rows += build_row(None, 0, "", "MCDB", lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.996)))
            m_rows += build_row(None, 0, "2%", "WB", lambda x: x['WB'].quantile(0.980))
            m_rows += build_row(None, 0, "", "MCDB", lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.980)))

            # --- ENSAMBLADO HTML (CLON DEL REPORTE) ---
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
                        <td style="border:none; text-align:left;"><b>Time Zone:</b> -5.0</td>
                        <td style="border:none; text-align:left;"><b>Time Period:</b> {period_display}</td>
                    </tr>
                </table>

                <table>
                    <tr><th colspan="12" class="header-blue">Annual Heating and Humidification Design Conditions</th></tr>
                    <tr class="gray-header">
                        <td rowspan="2">Coldest Month</td>
                        <td colspan="2">Heating DB (°C)</td>
                        <td colspan="6">Humidification DP / HR / MCDB</td>
                        <td colspan="3">Coldest month WS / MCDB</td>
                    </tr>
                    <tr class="gray-header">
                        <td>99.6%</td><td>99%</td>
                        <td>99.6% DP</td><td>HR</td><td>MCDB</td>
                        <td>99% DP</td><td>HR</td><td>MCDB</td>
                        <td>0.4% WS</td><td>1% WS</td><td>MCDB</td>
                    </tr>
                    <tr>
                        <td style="font-weight:bold;">{coldest_month}</td>
                        <td>{db_min_ann:.1f}</td><td>{df['DB'].quantile(0.010):.1f}</td>
                        <td>{df['DP'].quantile(0.004):.1f}</td><td>{mc(df, 'DP', 'HR', df['DP'].quantile(0.004)):.1f}</td><td>{mc(df, 'DP', 'DB', df['DP'].quantile(0.004)):.1f}</td>
                        <td>{df['DP'].quantile(0.010):.1f}</td><td>{mc(df, 'DP', 'HR', df['DP'].quantile(0.010)):.1f}</td><td>{mc(df, 'DP', 'DB', df['DP'].quantile(0.010)):.1f}</td>
                        <td>{df['WS'].quantile(0.996):.1f}</td><td>{df['WS'].quantile(0.990):.1f}</td><td>{mc(df, 'WS', 'DB', df['WS'].quantile(0.996)):.1f}</td>
                    </tr>
                </table>

                <table>
                    <tr><th colspan="16" class="header-blue">Annual Cooling, Dehumidification, and Enthalpy Design Conditions</th></tr>
                    <tr class="gray-header">
                        <td rowspan="2">Hottest Month</td><td rowspan="2">DB Range</td>
                        <td colspan="4">Cooling DB / MCWB (°C)</td>
                        <td colspan="4">Evaporation WB / MCDB (°C)</td>
                        <td colspan="3">Dehumid. DP/HR/MCDB</td>
                        <td colspan="3">Enthalpy / MCDB</td>
                    </tr>
                    <tr class="gray-header">
                        <td colspan="2">0.4%</td><td colspan="2">2%</td>
                        <td colspan="2">0.4%</td><td colspan="2">2%</td>
                        <td>0.4% DP</td><td>HR</td><td>MCDB</td>
                        <td>0.4% En</td><td>1% En</td><td>MCDB</td>
                    </tr>
                    <tr>
                        <td style="font-weight:bold;">{hottest_month}</td>
                        <td>{df[df['Month'] == hottest_month]['DB'].max() - df[df['Month'] == hottest_month]['DB'].min():.1f}</td>
                        <td>{db_max_ann:.1f}</td><td>{mc(df, 'DB', 'WB', db_max_ann):.1f}</td>
                        <td>{df['DB'].quantile(0.980):.1f}</td><td>{mc(df, 'DB', 'WB', df['DB'].quantile(0.980)):.1f}</td>
                        <td>{wb_max_ann:.1f}</td><td>{mc(df, 'WB', 'DB', wb_max_ann):.1f}</td>
                        <td>{df['WB'].quantile(0.980):.1f}</td><td>{mc(df, 'WB', 'DB', df['WB'].quantile(0.980)):.1f}</td>
                        <td>{dp_max_ann:.1f}</td><td>{mc(df, 'DP', 'HR', dp_max_ann):.1f}</td><td>{mc(df, 'DP', 'DB', dp_max_ann):.1f}</td>
                        <td>{enth_max_ann:.1f}</td><td>{df['Enth'].quantile(0.990):.1f}</td><td>{mc(df, 'Enth', 'DB', enth_max_ann):.1f}</td>
                    </tr>
                </table>

                <table>
                    <tr><th colspan="12" class="header-blue">Extreme Annual Design Conditions</th></tr>
                    <tr class="gray-header">
                        <td colspan="3">Extreme Annual WS (m/s)</td><td colspan="4">Extreme Annual Temp</td>
                        <td colspan="4">n-Year Return Period Values (N/A for TMY format)</td>
                    </tr>
                    <tr class="gray-header">
                        <td>1%</td><td>2.5%</td><td>5%</td>
                        <td>DB Mean Min/Max</td><td>Std Dev</td><td>WB Mean Min/Max</td><td>Std Dev</td>
                        <td>n=5</td><td>n=10</td><td>n=20</td><td>n=50</td>
                    </tr>
                    <tr>
                        <td>{df['WS'].quantile(0.990):.1f}</td><td>{df['WS'].quantile(0.975):.1f}</td><td>{df['WS'].quantile(0.950):.1f}</td>
                        <td>{df['DB'].min():.1f} / {df['DB'].max():.1f}</td><td>{df['DB'].std():.1f}</td>
                        <td>{df['WB'].min():.1f} / {df['WB'].max():.1f}</td><td>{df['WB'].std():.1f}</td>
                        <td>N/A</td><td>N/A</td><td>N/A</td><td>N/A</td>
                    </tr>
                </table>

                <table>
                    <tr><th colspan="16" class="header-blue">Monthly Climatic Design Conditions</th></tr>
                    <tr class="gray-header">
                        <td colspan="3">Parameters</td>
                        <td>Annual</td><td>Jan</td><td>Feb</td><td>Mar</td><td>Apr</td><td>May</td><td>Jun</td>
                        <td>Jul</td><td>Aug</td><td>Sep</td><td>Oct</td><td>Nov</td><td>Dec</td>
                    </tr>
                    {m_rows}
                </table>
            </body></html>
            """
            
            html_preview_final = html_base.replace("</head>", f"{css_preview}</head>")
            html_pdf_final = html_base.replace("</head>", f"{css_pdf}</head>")
            
            st.success("¡Matriz local procesada exitosamente!")
            
            with st.expander("👀 Vista Previa del Reporte de Diseño (EPW)", expanded=True):
                components.html(html_preview_final, height=600, scrolling=True)
            
            pdf_file = HTML(string=html_pdf_final).write_pdf()
            st.download_button(label="📥 Descargar Reporte (PDF Vertical)", data=pdf_file, file_name=f"Condiciones_Climaticas_EPW_{selected_city}.pdf", mime="application/pdf")
