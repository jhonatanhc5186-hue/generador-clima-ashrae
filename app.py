import streamlit as st
import pandas as pd
import numpy as np
import requests
import os
import re
import streamlit.components.v1 as components
from weasyprint import HTML

st.set_page_config(page_title="Generador de Reportes Climáticos", layout="wide")

# --- 1. FUNCIONES BASE Y GEOLOCALIZACIÓN ---
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

def get_location_name(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        res = requests.get(url, headers={'User-Agent': 'AppPeruClima/1.0'}, timeout=5).json()
        address = res.get('address', {})
        pais = address.get('country', 'PERÚ').upper()
        ciudad = address.get('city', address.get('town', address.get('village', address.get('county', 'UBICACIÓN DESCONOCIDA')))).upper()
        return f"{ciudad}, {pais}"
    except: 
        return f"LAT: {lat}, LON: {lon}"

# --- 2. MOTOR TERMODINÁMICO ---
def calc_wb(T, RH):
    return T * np.arctan(0.151977 * (RH + 8.313659)**0.5) + np.arctan(T + RH) - np.arctan(RH - 1.676331) + 0.00391838 * (RH)**1.5 * np.arctan(0.023101 * RH) - 4.686035

def calc_enthalpy(T, HR):
    return 1.006 * T + (HR/1000) * (2501 + 1.86 * T)

def mc(sub, base_col, target_col, t):
    h = sub[(sub[base_col] >= t - 0.2) & (sub[base_col] <= t + 0.2)]
    return h[target_col].mean() if not h.empty else sub[target_col].mean()

# --- 3. INTERFAZ TIPO NASA (CONTROLES IZQUIERDA / MAPA DERECHA) ---
st.markdown("<h2 style='text-align: center; color: #1f456e;'>NASA POWER | Data Access Viewer</h2>", unsafe_allow_html=True)
st.markdown("---")

col_params, col_map = st.columns([1, 2.5], gap="large")

with col_params:
    st.markdown("### Reports")
    modo = st.radio(
        "Source Method:", 
        ["📍 Satellite Coordinates (NASA)", "🏢 Local Station (EPW Data)"]
    )
    
    st.markdown("<br>", unsafe_allow_html=True)
    file_map = get_epw_mapping()

    if "Satellite" in modo:
        usar_local = False
        st.selectbox("Report Name *", ["Climate Design Conditions"], disabled=True)
        lat = st.number_input("Latitude *", value=-16.3410, format="%.4f")
        lon = st.number_input("Longitude *", value=-71.5830, format="%.4f")
        
        start_y = st.selectbox("Start Date *", list(range(2001, 2020)), index=0)
        end_y = st.selectbox("End Date *", list(range(2006, 2025)), index=18)
    else:
        usar_local = True
        selected_city = st.selectbox("Report Name (Local EPW) *", list(file_map.keys()))
        
        filename = file_map[selected_city]
        try:
            with open(f"data/{filename}", 'r', encoding='utf-8') as f:
                h_data = f.readline().split(',')
                lat_prev, lon_prev = float(h_data[6]), float(h_data[7])
        except:
            lat_prev, lon_prev = 0.0, 0.0
            
        lat = st.number_input("Latitude *", value=lat_prev, disabled=True, format="%.4f")
        lon = st.number_input("Longitude *", value=lon_prev, disabled=True, format="%.4f")

    st.markdown("<br>", unsafe_allow_html=True) 
    btn_generar = st.button("➔ Submit / Generar Reporte", type="primary", use_container_width=True)

with col_map:
    # MAPA INTERACTIVO
    st.markdown(f"<div style='text-align:right; font-size:12px; color:gray;'>Latitude: {lat:.4f} | Longitude: {lon:.4f}</div>", unsafe_allow_html=True)
    map_data = pd.DataFrame({'lat': [lat], 'lon': [lon]})
    st.map(map_data, zoom=8, use_container_width=True)

st.markdown("---")

# --- 4. CSS CLÓNICO NASA PARA REPORTES ---
css_base = """
<style>
    @page { size: A4 portrait; margin: 6mm; }
    body { font-family: 'Times New Roman', Times, serif; margin: 0; padding: 0; background-color: #ffffff; color: #000; }
    table { width: 100% !important; border-collapse: collapse !important; margin-bottom: 6px !important; table-layout: fixed !important; border: 1px solid #000; }
    th, td { border: 1px solid black !important; padding: 1px 2px !important; text-align: center !important; line-height: 1.1 !important; word-wrap: break-word !important; }
    .header-blue, th.nasa-blue { background-color: #0000cc !important; color: white !important; font-weight: bold; padding: 2px !important; border: 1px solid #0000cc !important; }
    .gray-header td { font-weight: bold; background-color: #ffffff !important; } 
    .title-bar { text-align: center; font-weight: bold; margin-bottom: 3px; color: #000; }
    .location-pin { text-align: center; font-weight: bold; margin-bottom: 6px; color: #000; }
    a { display: none !important; }
</style>
"""
css_pdf = css_base + "<style> body, td { font-size: 6px !important; } .header-blue, th.nasa-blue { font-size: 7px !important; } .title-bar { font-size: 11px !important; } .location-pin { font-size: 12px !important; } </style>"
css_preview = css_base + "<style> body, td { font-size: 11px !important; } .header-blue, th.nasa-blue { font-size: 13px !important; } .title-bar { font-size: 16px !important; } .location-pin { font-size: 15px !important; } table { margin-bottom: 15px !important; } </style>"

# --- 5. LÓGICA DE GENERACIÓN ---
if btn_generar:
    
    if not usar_local:
        with st.spinner("Conectando con servidores satelitales (Esto puede tomar hasta 45 segundos)..."):
            api_url = f"https://power.larc.nasa.gov/api/application/indicators/point?start={start_y}&end={end_y}&latitude={lat}&longitude={lon}&format=html&user=DAVE"
            try:
                respuesta = requests.get(api_url, timeout=45)
                
                if respuesta.status_code == 200:
                    html_crudo = respuesta.text
                    
                    html_limpio = re.sub(r'(?i)https?://power\.larc\.nasa\.gov[^\s<]*', '', html_crudo)
                    html_limpio = re.sub(r'POWER Climatic Design Conditions \(.*?\)', 'CONDICIONES CLIMÁTICAS DE DISEÑO', html_limpio)
                    html_limpio = html_limpio.replace("POWER Climatic Design Conditions", "CONDICIONES CLIMÁTICAS DE DISEÑO")
                    
                    loc_name = get_location_name(lat, lon)
                    pin_html = f"<div class='location-pin'><span style='color: #d9534f;'>📍</span> {loc_name} (WMO: SATELITAL)</div>"
                    html_limpio = html_limpio.replace("<table", f"{pin_html}\n<table", 1)
                    
                    html_preview_final = html_limpio.replace("</head>", "{css}</head>".format(css=css_preview))
                    html_pdf_final = html_limpio.replace("</head>", "{css}</head>".format(css=css_pdf))
                    
                    st.success("¡Matriz satelital procesada exitosamente!")
                    with st.expander("👀 Request Results / Vista Previa", expanded=True):
                        components.html(html_preview_final, height=700, scrolling=True)
                    
                    pdf_file = HTML(string=html_pdf_final).write_pdf()
                    st.download_button(label="📥 Descargar Reporte (PDF Vertical)", data=pdf_file, file_name=f"Condiciones_Climaticas_{lat}_{lon}.pdf", mime="application/pdf")
                
                elif respuesta.status_code == 422:
                    st.error("❌ ERROR MATEMÁTICO (HTTP 422): La NASA ha rechazado la solicitud. El rango de años seleccionado es insuficiente para calcular los periodos de retorno a 50 años. Asegúrate de tener al menos 10 años de diferencia (Ej. 2004 - 2024).")
                else: 
                    st.error(f"❌ Error de la API NASA (HTTP {respuesta.status_code}).")
            
            except Exception as e: 
                st.error("❌ Error de conexión: Tiempo de espera agotado. Los servidores están ocupados en este momento.")

    else:
        with st.spinner("Procesando archivo EPW y generando reporte de diseño..."):
            filename = file_map[selected_city]
            period_display = "TMYx"
            try:
                for p in filename.replace(".epw", "").split('.'):
                    if "-" in p and len(p) == 9 and p.split('-')[0].isdigit(): period_display = p
                with open(f"data/{filename}", 'r', encoding='utf-8') as f:
                    h_data = f.readline().split(',')
                    wmo_display = h_data[5].strip()
                    lat_val, lon_val, alt_display = float(h_data[6]), float(h_data[7]), float(h_data[9].strip())
            except: 
                wmo_display, lat_val, lon_val, alt_display = "000000", 0, 0, 0

            df = pd.read_csv(f"data/{filename}", skiprows=8, header=None, usecols=[1,2,3,6,7,8,9,13,14,15,21,33], names=['Month','Day','Hour','DB','DP','RH','Press','GloHorz','DirNorm','DifHorz','WS','Precip'])
            df['Press_kPa'] = df['Press'] / 1000
            df['Precip'] = pd.to_numeric(df['Precip'], errors='coerce').fillna(0).apply(lambda x: 0 if x > 900 else x)
            df['Year'] = 2024
            
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
            m_rows += build_row([("Temperatures,<br>Degree-Days and<br>Degree-Hours<br>(°C)", 8, 1, True), ("DBAvg", 1, 2, False)], lambda x: x['DB'].mean())
            m_rows += build_row([("DBStd", 1, 2, False)], lambda x: x['DB'].std())
            m_rows += build_row([("HDD10.0", 1, 2, False)], lambda x: (10.0 - x['DB']).clip(lower=0).sum() / 24)
            m_rows += build_row([("HDD18.3", 1, 2, False)], lambda x: (18.3 - x['DB']).clip(lower=0).sum() / 24)
            m_rows += build_row([("CDD10.0", 1, 2, False)], lambda x: (x['DB'] - 10.0).clip(lower=0).sum() / 24)
            m_rows += build_row([("CDD18.3", 1, 2, False)], lambda x: (x['DB'] - 18.3).clip(lower=0).sum() / 24)
            m_rows += build_row([("CDH23.3", 1, 2, False)], lambda x: (x['DB'] - 23.3).clip(lower=0).sum())
            m_rows += build_row([("CDH26.7", 1, 2, False)], lambda x: (x['DB'] - 26.7).clip(lower=0).sum())
            
            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([("Wind (m/s)", 1, 1, True), ("WSAvg", 1, 2, False)], lambda x: x['WS'].mean())
            
            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([("Precipitation<br>(mm)", 4, 1, True), ("PrecAvg", 1, 2, False)], lambda x: x['Precip'].sum())
            m_rows += build_row([("PrecMax", 1, 2, False)], lambda x: x['Precip'].sum()) 
            m_rows += build_row([("PrecMin", 1, 2, False)], lambda x: x['Precip'].sum()) 
            m_rows += build_row([("PrecStd", 1, 2, False)], lambda x: 0.0)
            
            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([("Monthly Design<br>Dry Bulb and Mean<br>Coincident Wet<br>Bulb Temperatures<br>(°C)", 8, 1, True), ("0.4%", 2, 1, False), ("DB", 1, 1, False)], lambda x: x['DB'].quantile(0.996))
            m_rows += build_row([("MCWB", 1, 1, False)], lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.996)))
            m_rows += build_row([("2%", 2, 1, False), ("DB", 1, 1, False)], lambda x: x['DB'].quantile(0.980))
            m_rows += build_row([("MCWB", 1, 1, False)], lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.980)))
            m_rows += build_row([("5%", 2, 1, False), ("DB", 1, 1, False)], lambda x: x['DB'].quantile(0.950))
            m_rows += build_row([("MCWB", 1, 1, False)], lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.950)))
            m_rows += build_row([("10%", 2, 1, False), ("DB", 1, 1, False)], lambda x: x['DB'].quantile(0.900))
            m_rows += build_row([("MCWB", 1, 1, False)], lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.900)))

            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([("Monthly Design<br>Wet Bulb and Mean<br>Coincident Dry<br>Bulb Temperatures<br>(°C)", 8, 1, True), ("0.4%", 2, 1, False), ("WB", 1, 1, False)], lambda x: x['WB'].quantile(0.996))
            m_rows += build_row([("MCDB", 1, 1, False)], lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.996)))
            m_rows += build_row([("2%", 2, 1, False), ("WB", 1, 1, False)], lambda x: x['WB'].quantile(0.980))
            m_rows += build_row([("MCDB", 1, 1, False)], lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.980)))
            m_rows += build_row([("5%", 2, 1, False), ("WB", 1, 1, False)], lambda x: x['WB'].quantile(0.950))
            m_rows += build_row([("MCDB", 1, 1, False)], lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.950)))
            m_rows += build_row([("10%", 2, 1, False), ("WB", 1, 1, False)], lambda x: x['WB'].quantile(0.900))
            m_rows += build_row([("MCDB", 1, 1, False)], lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.900)))

            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([("Mean Daily<br>Temperature Range<br>(°C)", 5, 1, True), ("MDBR", 1, 2, False)], lambda x: (x.groupby(x.index // 24)['DB'].max() - x.groupby(x.index // 24)['DB'].min()).mean())
            m_rows += build_row([("5% DB", 2, 1, False), ("MCDBR", 1, 1, False)], lambda x: (x.groupby(x.index // 24)['DB'].max() - x.groupby(x.index // 24)['DB'].min()).quantile(0.95))
            m_rows += build_row([("MCWBR", 1, 1, False)], lambda x: (x.groupby(x.index // 24)['WB'].max() - x.groupby(x.index // 24)['WB'].min()).mean())
            m_rows += build_row([("5% WB", 2, 1, False), ("MCDBR", 1, 1, False)], lambda x: (x.groupby(x.index // 24)['DB'].max() - x.groupby(x.index // 24)['DB'].min()).mean())
            m_rows += build_row([("MCWBR", 1, 1, False)], lambda x: (x.groupby(x.index // 24)['WB'].max() - x.groupby(x.index // 24)['WB'].min()).quantile(0.95))

            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([("Clear Sky Solar<br>Irradiance (W m-2)", 2, 1, True), ("Ebn,noon", 1, 2, False)], lambda x: x[x['Hour'].between(11,13)]['DirNorm'].mean() if not x.empty else 0)
            m_rows += build_row([("Edn,noon", 1, 2, False)], lambda x: x[x['Hour'].between(11,13)]['DifHorz'].mean() if not x.empty else 0)
            
            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([("All-Sky Solar<br>Radiation (W m-2)", 2, 1, True), ("RadAvg", 1, 2, False)], lambda x: (x['GloHorz'].mean() * 24 / 1000) if not x.empty else 0)
            m_rows += build_row([("RadStd", 1, 2, False)], lambda x: (x['GloHorz'].std() * 24 / 1000) if not x.empty else 0)

            city_only = selected_city.split('-')[-1].strip().upper()
            pin_html = f"<div class='location-pin'><span style='color: #d9534f;'>📍</span> {city_only}, PERÚ (WMO: {wmo_display})</div>"

            html_base = f"""
            <html><head></head>
            <body>
                <div class="title-bar">CONDICIONES CLIMÁTICAS DE DISEÑO</div>
                {pin_html}
                
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
            
            html_preview_final = html_base.replace("</head>", "{css}</head>".format(css=css_preview))
            html_pdf_final = html_base.replace("</head>", "{css}</head>".format(css=css_pdf))
            
            st.success("¡Reporte procesado exitosamente!")
            
            with st.expander("👀 Request Results / Vista Previa", expanded=True):
                components.html(html_preview_final, height=700, scrolling=True)
            
            pdf_file = HTML(string=html_pdf_final).write_pdf()
            st.download_button(label="📥 Descargar Reporte (PDF Vertical)", data=pdf_file, file_name=f"Condiciones_Climaticas_EPW_{selected_city}.pdf", mime="application/pdf")
