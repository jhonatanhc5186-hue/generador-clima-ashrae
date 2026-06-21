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

# --- 2. MOTOR TERMODINÁMICO ---
def calc_wb(T, RH):
    return T * np.arctan(0.151977 * (RH + 8.313659)**0.5) + np.arctan(T + RH) - np.arctan(RH - 1.676331) + 0.00391838 * (RH)**1.5 * np.arctan(0.023101 * RH) - 4.686035

def calc_enthalpy(T, HR):
    return 1.006 * T + (HR/1000) * (2501 + 1.86 * T)

def mc(sub, base_col, target_col, t):
    h = sub[(sub[base_col] >= t - 0.2) & (sub[base_col] <= t + 0.2)]
    return h[target_col].mean() if not h.empty else sub[target_col].mean()

# --- 3. INTERFAZ ---
modo = st.radio(
    "Seleccione la fuente de datos (Formato Oficial NASA POWER):", 
    ["📍 Búsqueda por Coordenadas (Data Satelital Directa)", "🏢 Estación Local (Clonación desde Archivos EPW)"], 
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

# --- 4. CSS CLÓNICO NASA ---
css_base = """
<style>
    @page { size: A4 portrait; margin: 6mm; }
    body { font-family: 'Times New Roman', Times, serif; margin: 0; padding: 0; background-color: #ffffff; color: #000; }
    table { width: 100% !important; border-collapse: collapse !important; margin-bottom: 6px !important; table-layout: fixed !important; border: 1px solid #000; }
    th, td { border: 1px solid black !important; padding: 1px 2px !important; text-align: center !important; line-height: 1.1 !important; word-wrap: break-word !important; }
    .header-blue, th.nasa-blue { background-color: #0000cc !important; color: white !important; font-weight: bold; padding: 2px !important; }
    .divider-blue { background-color: #0000cc !important; height: 3px !important; padding: 0 !important; border: 1px solid #0000cc !important; }
    .gray-header td { font-weight: bold; background-color: #ffffff !important; } 
    .title-bar { text-align: center; font-weight: bold; margin-bottom: 5px; color: #000; }
    a { display: none !important; }
</style>
"""

# Escalado dinámico: Pequeño para PDF (A4 Vertical), Grande para la vista web
css_pdf = css_base + "<style> body, td { font-size: 6px !important; } .header-blue, th.nasa-blue { font-size: 7px !important; } .title-bar { font-size: 9px !important; } </style>"
css_preview = css_base + "<style> body, td { font-size: 11px !important; } .header-blue, th.nasa-blue { font-size: 13px !important; } .title-bar { font-size: 16px !important; } table { margin-bottom: 15px !important; } </style>"

if st.button("Generar Reporte Maestro"):
    
    if not usar_local:
        # =========================================================
        # MODO COORDENADAS: EXTRACCIÓN HTML DE LA NASA
        # =========================================================
        with st.spinner("Conectando con servidores satelitales..."):
            api_url = f"https://power.larc.nasa.gov/api/application/indicators/point?start={start_y}&end={end_y}&latitude={lat}&longitude={lon}&format=html&user=DAVE"
            try:
                respuesta = requests.get(api_url, timeout=30)
                if respuesta.status_code == 200:
                    html_crudo = respuesta.text
                    
                    # Filtro de Privacidad
                    html_limpio = re.sub(r'(?i)https?://power\.larc\.nasa\.gov[^\s<]*', '', html_crudo)
                    html_limpio = re.sub(r'POWER Climatic Design Conditions \(.*?\)', 'CONDICIONES CLIMÁTICAS DE DISEÑO', html_limpio)
                    html_limpio = html_limpio.replace("POWER Climatic Design Conditions", "CONDICIONES CLIMÁTICAS DE DISEÑO")
                    
                    html_preview_final = html_limpio.replace("</head>", f"{css_preview}</head>")
                    html_pdf_final = html_limpio.replace("</head>", f"{css_pdf}</head>")
                    
                    st.success("¡Matriz satelital procesada exitosamente!")
                    with st.expander("👀 Vista Previa del Reporte Oficial", expanded=True):
                        components.html(html_preview_final, height=700, scrolling=True)
                    
                    pdf_file = HTML(string=html_pdf_final).write_pdf()
                    st.download_button(label="📥 Descargar Reporte (PDF Vertical)", data=pdf_file, file_name=f"Condiciones_Climaticas_{lat}_{lon}.pdf", mime="application/pdf")
                else: st.error("Error al obtener información satelital de la NASA.")
            except: st.error("Error de conexión durante el procesamiento.")

    else:
        # =========================================================
        # MODO EPW LOCAL: CLONACIÓN MATEMÁTICA Y VISUAL 1:1
        # =========================================================
        with st.spinner("Procesando motor EPW y clonando diseño de matriz..."):
            filename = file_map[selected_city]
            period_display = "TMYx"
            try:
                for p in filename.replace(".epw", "").split('.'):
                    if "-" in p and len(p) == 9 and p.split('-')[0].isdigit(): period_display = p
                with open(f"data/{filename}", 'r', encoding='utf-8') as f:
                    h_data = f.readline().split(',')
                    lat_val, lon_val, alt_display = float(h_data[6]), float(h_data[7]), float(h_data[9].strip())
            except: lat_val, lon_val, alt_display = 0, 0, 0

            df = pd.read_csv(f"data/{filename}", skiprows=8, header=None, usecols=[1,2,3,6,7,8,9,13,14,15,21,33], names=['Month','Day','Hour','DB','DP','RH','Press','GloHorz','DirNorm','DifHorz','WS','Precip'])
            df['Press_kPa'] = df['Press'] / 1000
            df['Precip'] = pd.to_numeric(df['Precip'], errors='coerce').fillna(0).apply(lambda x: 0 if x > 900 else x)
            df['Year'] = 2024
            
            # Termodinámica Psicrométrica
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

            all_data = [df] + [df[df['Month'] == m] for m in range(1, 13)]
            
            # Función constructora de filas flexibles con negritas donde corresponda
            def build_row(headers, func):
                r = "<tr>"
                for text, rs, cs, is_bold in headers:
                    weight = "bold" if is_bold else "normal"
                    r += f"<td rowspan='{rs}' colspan='{cs}' style='font-weight:{weight};'>{text}</td>"
                vals = [func(d) if not d.empty else 0 for d in all_data]
                for v in vals:
                    r += f"<td>{v:.1f}</td>" if isinstance(v, float) else f"<td>{v}</td>"
                r += "</tr>"
                return r

            m_rows = ""
            # 1. Temperatures
            m_rows += build_row([("Temperatures,<br>Degree-Days and<br>Degree-Hours<br>(°C)", 8, 1, True), ("DBAvg", 1, 2, False)], lambda x: x['DB'].mean())
            m_rows += build_row([("DBStd", 1, 2, False)], lambda x: x['DB'].std())
            m_rows += build_row([("HDD10.0", 1, 2, False)], lambda x: (10.0 - x['DB']).clip(lower=0).sum() / 24)
            m_rows += build_m_row([("HDD18.3", 1, 2, False)], lambda x: (18.3 - x['DB']).clip(lower=0).sum() / 24)
            m_rows += build_row([("CDD10.0", 1, 2, False)], lambda x: (x['DB'] - 10.0).clip(lower=0).sum() / 24)
            m_rows += build_row([("CDD18.3", 1, 2, False)], lambda x: (x['DB'] - 18.3).clip(lower=0).sum() / 24)
            m_rows += build_row([("CDH23.3", 1, 2, False)], lambda x: (x['DB'] - 23.3).clip(lower=0).sum())
            m_rows += build_row([("CDH26.7", 1, 2, False)], lambda x: (x['DB'] - 26.7).clip(lower=0).sum())
            
            # 2. Wind
            m_rows += "<tr><td colspan='16' class='divider-blue'></td></tr>"
            m_rows += build_row([("Wind (m/s)", 1, 1, True), ("WSAvg", 1, 2, False)], lambda x: x['WS'].mean())
            
            # 3. Precipitation
            m_rows += "<tr><td colspan='16' class='divider-blue'></td></tr>"
            m_rows += build_row([("Precipitation<br>(mm)", 4, 1, True), ("PrecAvg", 1, 2, False)], lambda x: x['Precip'].sum())
            m_rows += build_row([("PrecMax", 1, 2, False)], lambda x: x['Precip'].sum()) 
            m_rows += build_row([("PrecMin", 1, 2, False)], lambda x: x['Precip'].sum()) 
            m_rows += build_row([("PrecStd", 1, 2, False)], lambda x: 0.0)
            
            # 4. Monthly Design DB & MCWB
            m_rows += "<tr><td colspan='16' class='divider-blue'></td></tr>"
            m_rows += build_row([("Monthly Design<br>Dry Bulb and Mean<br>Coincident Wet<br>Bulb Temperatures<br>(°C)", 8, 1, True), ("0.4%", 2, 1, False), ("DB", 1, 1, False)], lambda x: x['DB'].quantile(0.996))
            m_rows += build_row([("MCWB", 1, 1, False)], lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.996)))
            m_rows += build_row([("2%", 2, 1, False), ("DB", 1, 1, False)], lambda x: x['DB'].quantile(0.980))
            m_rows += build_row([("MCWB", 1, 1, False)], lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.980)))
            m_rows += build_row([("5%", 2, 1, False), ("DB", 1, 1, False)], lambda x: x['DB'].quantile(0.950))
            m_rows += build_row([("MCWB", 1, 1, False)], lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.950)))
            m_rows += build_row([("10%", 2, 1, False), ("DB", 1, 1, False)], lambda x: x['DB'].quantile(0.900))
            m_rows += build_row([("MCWB", 1, 1, False)], lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.900)))

            # 5. Monthly Design WB & MCDB
            m_rows += "<tr><td colspan='16' class='divider-blue'></td></tr>"
            m_rows += build_row([("Monthly Design<br>Wet Bulb and Mean<br>Coincident Dry<br>Bulb Temperatures<br>(°C)", 8, 1, True), ("0.4%", 2, 1, False), ("WB", 1, 1, False)], lambda x: x['WB'].quantile(0.996))
            m_rows += build_row([("MCDB", 1, 1, False)], lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.996)))
            m_rows += build_row([("2%", 2, 1, False), ("WB", 1, 1, False)], lambda x: x['WB'].quantile(0.980))
            m_rows += build_row([("MCDB", 1, 1, False)], lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.980)))
            m_rows += build_row([("5%", 2, 1, False), ("WB", 1, 1, False)], lambda x: x['WB'].quantile(0.950))
            m_rows += build_row([("MCDB", 1, 1, False)], lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.950)))
            m_rows += build_row([("10%", 2, 1, False), ("WB", 1, 1, False)], lambda x: x['WB'].quantile(0.900))
            m_rows += build_row([("MCDB", 1, 1, False)], lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.900)))

            # 6. Mean Daily Temperature Range
            m_rows += "<tr><td colspan='16' class='divider-blue'></td></tr>"
            m_rows += build_row([("Mean Daily<br>Temperature Range<br>(°C)", 5, 1, True), ("MDBR", 1, 2, False)], lambda x: (x.groupby(x.index // 24)['DB'].max() - x.groupby(x.index // 24)['DB'].min()).mean())
            m_rows += build_row([("5% DB", 2, 1, False), ("MCDBR", 1, 1, False)], lambda x: (x.groupby(x.index // 24)['DB'].max() - x.groupby(x.index // 24)['DB'].min()).quantile(0.95))
            m_rows += build_row([("MCWBR", 1, 1, False)], lambda x: (x.groupby(x.index // 24)['WB'].max() - x.groupby(x.index // 24)['WB'].min()).mean())
            m_rows += build_row([("5% WB", 2, 1, False), ("MCDBR", 1, 1, False)], lambda x: (x.groupby(x.index // 24)['DB'].max() - x.groupby(x.index // 24)['DB'].min()).mean())
            m_rows += build_row([("MCWBR", 1, 1, False)], lambda x: (x.groupby(x.index // 24)['WB'].max() - x.groupby(x.index // 24)['WB'].min()).quantile(0.95))

            # 7. Solar Radiation
            m_rows += "<tr><td colspan='16' class='divider-blue'></td></tr>"
            m_rows += build_row([("Clear Sky Solar<br>Irradiance (W m-2)", 2, 1, True), ("Ebn,noon", 1, 2, False)], lambda x: x[x['Hour'].between(11,13)]['DirNorm'].mean() if not x.empty else 0)
            m_rows += build_row([("Edn,noon", 1, 2, False)], lambda x: x[x['Hour'].between(11,13)]['DifHorz'].mean() if not x.empty else 0)
            
            m_rows += "<tr><td colspan='16' class='divider-blue'></td></tr>"
            m_rows += build_row([("All-Sky Solar<br>Radiation (W m-2)", 2, 1, True), ("RadAvg", 1, 2, False)], lambda x: (x['GloHorz'].mean() * 24 / 1000) if not x.empty else 0)
            m_rows += build_row([("RadStd", 1, 2, False)], lambda x: (x['GloHorz'].std() * 24 / 1000) if not x.empty else 0)

            # --- ENSAMBLADO HTML FINAL EPW ---
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
                        <td style="border:none; text-align:right;">Note: Local EPW Data</td>
                    </tr>
                </table>

                <table>
                    <tr><th colspan="15" class="header-blue">Annual Heating and Humidification Design Conditions</th></tr>
                    <tr class="gray-header">
                        <td rowspan="2">Coldest<br>Month</td>
                        <td colspan="2">Heating DB (°C)</td>
                        <td colspan="6">Humidification DP / MCDB and HR (°C)</td>
                        <td colspan="4">Coldest month WS / MCDB (°C)</td>
                        <td colspan="2">MCWS/PCWD to<br>99.6% DB (°C)</td>
                    </tr>
                    <tr class="gray-header">
                        <td>99.6%</td><td>99%</td>
                        <td>99.6% DP</td><td>HR</td><td>MCDB</td>
                        <td>99% DP</td><td>HR</td><td>MCDB</td>
                        <td>0.4% WS</td><td>MCDB</td><td>1% WS</td><td>MCDB</td>
                        <td>MCWS</td><td>PCWD</td>
                    </tr>
                    <tr>
                        <td style="font-weight:bold;">{coldest_month}</td>
                        <td>{db_min_ann:.1f}</td><td>{df['DB'].quantile(0.010):.1f}</td>
                        <td>{df['DP'].quantile(0.004):.1f}</td><td>{mc(df, 'DP', 'HR', df['DP'].quantile(0.004)):.1f}</td><td>{mc(df, 'DP', 'DB', df['DP'].quantile(0.004)):.1f}</td>
                        <td>{df['DP'].quantile(0.010):.1f}</td><td>{mc(df, 'DP', 'HR', df['DP'].quantile(0.010)):.1f}</td><td>{mc(df, 'DP', 'DB', df['DP'].quantile(0.010)):.1f}</td>
                        <td>{df['WS'].quantile(0.996):.1f}</td><td>{mc(df, 'WS', 'DB', df['WS'].quantile(0.996)):.1f}</td>
                        <td>{df['WS'].quantile(0.990):.1f}</td><td>{mc(df, 'WS', 'DB', df['WS'].quantile(0.990)):.1f}</td>
                        <td>{mc(df, 'DB', 'WS', db_min_ann):.1f}</td><td>N/A</td>
                    </tr>
                </table>

                <table>
                    <tr><th colspan="17" class="header-blue">Annual Cooling, Dehumidification, and Enthalpy Design Conditions</th></tr>
                    <tr class="gray-header">
                        <td rowspan="2">Hottest<br>Month</td><td rowspan="2">Hottest<br>Month<br>DB Range</td>
                        <td colspan="4">Cooling DB / MCWB (°C)</td>
                        <td colspan="4">Evaporation WB / MCDB (°C)</td>
                        <td colspan="3">Dehumid. DP/MCDB and HR (°C)</td>
                        <td colspan="3">Enthalpy / MCDB (°C)</td>
                        <td rowspan="2">Ext.<br>Max WB<br>(°C)</td>
                    </tr>
                    <tr class="gray-header">
                        <td colspan="2">0.4%</td><td colspan="2">2%</td>
                        <td colspan="2">0.4%</td><td colspan="2">2%</td>
                        <td>0.4% DP</td><td>HR</td><td>MCDB</td>
                        <td>0.4% Enth</td><td>1% Enth</td><td>MCDB</td>
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
                        <td>{df['WB'].max():.1f}</td>
                    </tr>
                </table>

                <table>
                    <tr><th colspan="12" class="header-blue">Extreme Annual Design Conditions</th></tr>
                    <tr class="gray-header">
                        <td colspan="3">Extreme Annual WS (m/s)</td><td colspan="4">Extreme Annual Temperature (°C)</td>
                        <td colspan="4">n-Year Return Period Values of Extreme Temperature (°C)</td>
                    </tr>
                    <tr class="gray-header">
                        <td>1%</td><td>2.5%</td><td>5%</td>
                        <td>DB Mean Min/Max</td><td>Standard deviation</td><td>WB Mean Min/Max</td><td>Standard deviation</td>
                        <td>n=5 years</td><td>n=10 years</td><td>n=20 years</td><td>n=50 years</td>
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
            
            st.success("¡Matriz local clonada y renderizada exitosamente!")
            
            with st.expander("👀 Vista Previa del Reporte Clonado (Data EPW)", expanded=True):
                components.html(html_preview_final, height=700, scrolling=True)
            
            pdf_file = HTML(string=html_pdf_final).write_pdf()
            st.download_button(label="📥 Descargar Reporte (PDF Vertical)", data=pdf_file, file_name=f"Condiciones_Climaticas_EPW_{selected_city}.pdf", mime="application/pdf")
