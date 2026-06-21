import streamlit as st
import pandas as pd
import numpy as np
import requests
import os
from weasyprint import HTML

st.set_page_config(page_title="Generador de Reportes Climáticos", layout="wide")
st.title("🌍 Generador de Reportes: Condiciones Climáticas de Diseño (Estilo NASA POWER)")

# --- FUNCIONES BASE ---
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
            subparts = parts[2].split('.')
            city_words = []
            for p in subparts:
                if p in ['AP', 'Intl', 'TMYx'] or p.isdigit() or ('-' in p and p.split('-')[0].isdigit()): break
                city_words.append(p)
            ciudad = " ".join(city_words).split('-')[0].strip() 
            if ciudad == "Tacna": departamento = "Tacna"
            if ciudad == "Ilo": departamento = "Moquegua"
            return f"{pais} - {departamento} - {ciudad}"
        return filename.replace(".epw", "")
    except: return filename

def get_location_name(lat, lon):
    try:
        res = requests.get(f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json", headers={'User-Agent': 'AppPeru'}, timeout=5).json()
        address = res.get('address', {})
        pais = address.get('country', 'Perú')
        departamento = address.get('state', address.get('region', ''))
        ciudad = address.get('city', address.get('town', address.get('village', 'Ubicación Desconocida')))
        return f"{pais} - {departamento} - {ciudad}" if departamento else f"{pais} - {ciudad}"
    except: return f"Coordenadas [Lat: {lat}, Lon: {lon}]"

def calc_stdp(elev_m):
    try: return f"{101.325 * (1 - 2.25577e-5 * float(elev_m))**5.25588:.2f}"
    except: return "101.32"

def format_coord(val, is_lat):
    try:
        v = float(val)
        return f"{abs(v):.4f}{'N' if v >= 0 else 'S'}" if is_lat else f"{abs(v):.4f}{'E' if v >= 0 else 'W'}"
    except: return str(val)

def get_epw_mapping():
    if not os.path.exists("data"): return {}
    return {clean_city_name(f): f for f in sorted([f for f in os.listdir("data") if f.endswith(".epw")])}

# --- INTERFAZ STREAMLIT ---
modo = st.radio("Método de Generación (Formato Matriz Avanzada NASA):", ["🏢 Estación Local (EPW)", "📍 Coordenadas NASA"], horizontal=True)
st.markdown("---") 

col1, col2, col3 = st.columns(3)
file_map = get_epw_mapping()

if "Estación" in modo:
    usar_local = True
    selected_city = col1.selectbox("Ciudad:", list(file_map.keys()))
    lat = col2.number_input("Latitud", value=0.0000, disabled=True)
    lon = col3.number_input("Longitud", value=0.0000, disabled=True)
else:
    usar_local = False
    selected_city = None
    col1.info("📅 Rango NASA: 2001 - 2024")
    lat = col2.number_input("Latitud", value=-9.5653, format="%.4f")
    lon = col3.number_input("Longitud", value=-77.0364, format="%.4f")

st.markdown("<br>", unsafe_allow_html=True) 

if st.button("Generar MEGA REPORTE VERTICAL"):
    with st.spinner("Descargando matriz histórica y procesando ingeniería térmica... (Puede tardar ~40 segundos)"):
        
        # EXTRACCIÓN Y PSICROMETRÍA
        if usar_local:
            filename = file_map[selected_city]
            city_display, period_display = selected_city.upper(), "TMYx"
            try:
                for p in filename.replace(".epw", "").split('.'):
                    if "-" in p and len(p) == 9 and p.split('-')[0].isdigit(): period_display = p
                with open(f"data/{filename}", 'r', encoding='utf-8') as f:
                    h_data = f.readline().split(',')
                    wmo_display, lat_val, lon_val, alt_display = h_data[5].strip(), float(h_data[6]), float(h_data[7]), h_data[9].strip()
            except: lat_val, lon_val, alt_display = 0, 0, 0

            df = pd.read_csv(f"data/{filename}", skiprows=8, header=None, usecols=[1,2,6,7,9,21], names=['Month', 'Day', 'DB', 'DP', 'Press', 'WS'])
            df['Press_kPa'] = df['Press'] / 1000
            df['Year'] = 2024
            lat, lon = lat_val, lon_val
            fuente = f"Matriz generada desde archivo EPW Local. {len(df)} horas procesadas."

        else:
            city_display, wmo_display, period_display = get_location_name(lat, lon).upper(), "SATELITAL", "2001 - 2024"
            dfs = []
            for y in range(2001, 2025):
                url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET,T2MDEW,WS10M,PS&community=SB&longitude={lon}&latitude={lat}&start={y}0101&end={y}1231&format=JSON"
                try:
                    res = requests.get(url, timeout=15).json()
                    if y == 2001 and 'geometry' in res: alt_display = str(round(res['geometry']['coordinates'][2], 1))
                    props = res['properties']['parameter']
                    t_df = pd.DataFrame({'DB': list(props['T2M'].values()), 'WB': list(props['T2MWET'].values()), 'DP': list(props['T2MDEW'].values()), 'WS': list(props['WS10M'].values()), 'Press_kPa': list(props['PS'].values())})
                    t_df['Month'] = pd.date_range(start=f"{y}-01-01", periods=len(t_df), freq='h').month
                    t_df['Year'] = y
                    dfs.append(t_df)
                except: continue
            df = pd.concat(dfs, ignore_index=True)
            fuente = f"Generado desde API Satelital NASA ({period_display}). Extracción de {len(df):,} horas continuas."

        # TERMODINÁMICA EXACTA (Presión de Vapor, HR y Entalpía)
        df['Pv'] = 0.61078 * np.exp(17.27 * df['DP'] / (df['DP'] + 237.3))
        df['HR'] = 1000 * 0.62198 * df['Pv'] / (df['Press_kPa'] - df['Pv']) # Ratio de Humedad g/kg
        df['Enth'] = 1.006 * df['DB'] + (df['HR']/1000) * (2501 + 1.86 * df['DB']) # Entalpía kJ/kg
        
        if usar_local:
            # Fórmula Stull para aproximar WB si no viene directo del EPW
            P_sat = 0.61078 * np.exp(17.27 * df['DB'] / (df['DB'] + 237.3))
            df['RH'] = 100 * (df['Pv'] / P_sat)
            df['WB'] = df['DB'] * np.arctan(0.151977 * (df['RH'] + 8.313659)**0.5) + np.arctan(df['DB'] + df['RH']) - np.arctan(df['RH'] - 1.676331) + 0.00391838 * (df['RH'])**1.5 * np.arctan(0.023101 * df['RH']) - 4.686035

        # FUNCIÓN COINCIDENTE (MC)
        def mc(sub, base_col, target_col, t):
            h = sub[(sub[base_col] >= t - 0.2) & (sub[base_col] <= t + 0.2)]
            return h[target_col].mean() if not h.empty else sub[target_col].mean()

        # PERIODOS DE RETORNO Y EXTREMOS ANUALES
        ann_max_db, ann_min_db = df.groupby('Year')['DB'].max(), df.groupby('Year')['DB'].min()
        ann_max_wb, ann_min_wb = df.groupby('Year')['WB'].max(), df.groupby('Year')['WB'].min()
        
        def get_rp_max(s, t): return s.quantile(1 - 1/t) if len(s) > 1 else s.max()
        def get_rp_min(s, t): return s.quantile(1/t) if len(s) > 1 else s.min()

        db_max_ann, db_min_ann = df['DB'].quantile(0.996), df['DB'].quantile(0.004)
        wb_max_ann = df['WB'].quantile(0.996)
        dp_max_ann = df['DP'].quantile(0.996)
        enth_max_ann = df['Enth'].quantile(0.996)
        
        hottest_month = df.groupby('Month')['DB'].mean().idxmax()
        coldest_month = df.groupby('Month')['DB'].mean().idxmin()

        # CÁLCULOS MENSUALES
        m_rows = ""
        for m in range(1, 13):
            sub = df[df['Month'] == m]
            if sub.empty: continue
            
            hdd10 = sub['DB'].apply(lambda x: max(0, 10.0 - x)).sum() / len(sub['Year'].unique()) / 24
            hdd18 = sub['DB'].apply(lambda x: max(0, 18.3 - x)).sum() / len(sub['Year'].unique()) / 24
            cdd10 = sub['DB'].apply(lambda x: max(0, x - 10.0)).sum() / len(sub['Year'].unique()) / 24
            cdd18 = sub['DB'].apply(lambda x: max(0, x - 18.3)).sum() / len(sub['Year'].unique()) / 24
            cdh23 = sub['DB'].apply(lambda x: max(0, x - 23.3)).sum() / len(sub['Year'].unique())
            cdh26 = sub['DB'].apply(lambda x: max(0, x - 26.7)).sum() / len(sub['Year'].unique())
            
            db04, db20, db50, db10 = sub['DB'].quantile(0.996), sub['DB'].quantile(0.980), sub['DB'].quantile(0.950), sub['DB'].quantile(0.900)
            wb04, wb20, wb50, wb10 = sub['WB'].quantile(0.996), sub['WB'].quantile(0.980), sub['WB'].quantile(0.950), sub['WB'].quantile(0.900)
            mdbr = (sub.groupby([sub['Year'], sub.index // 24])['DB'].max() - sub.groupby([sub['Year'], sub.index // 24])['DB'].min()).mean()
            
            m_rows += f"""
            <tr>
                <td style="font-weight:bold; background:#fff;">{m}</td>
                <td>{sub['DB'].mean():.1f}</td><td>{sub['DB'].std():.1f}</td>
                <td>{hdd10:.0f}</td><td>{hdd18:.0f}</td><td>{cdd10:.0f}</td><td>{cdd18:.0f}</td><td>{cdh23:.0f}</td><td>{cdh26:.0f}</td>
                <td>{sub['WS'].mean():.1f}</td>
                <td style="background:#eaf1f8;">{db04:.1f}</td><td style="background:#eaf1f8;">{mc(sub, 'DB', 'WB', db04):.1f}</td>
                <td style="background:#eaf1f8;">{db20:.1f}</td><td style="background:#eaf1f8;">{mc(sub, 'DB', 'WB', db20):.1f}</td>
                <td style="background:#eaf1f8;">{db50:.1f}</td><td style="background:#eaf1f8;">{mc(sub, 'DB', 'WB', db50):.1f}</td>
                <td style="background:#eaf1f8;">{db10:.1f}</td><td style="background:#eaf1f8;">{mc(sub, 'DB', 'WB', db10):.1f}</td>
                <td style="background:#fff4e6;">{wb04:.1f}</td><td style="background:#fff4e6;">{mc(sub, 'WB', 'DB', wb04):.1f}</td>
                <td style="background:#fff4e6;">{wb20:.1f}</td><td style="background:#fff4e6;">{mc(sub, 'WB', 'DB', wb20):.1f}</td>
                <td style="background:#fff4e6;">{wb50:.1f}</td><td style="background:#fff4e6;">{mc(sub, 'WB', 'DB', wb50):.1f}</td>
                <td style="background:#fff4e6;">{wb10:.1f}</td><td style="background:#fff4e6;">{mc(sub, 'WB', 'DB', wb10):.1f}</td>
                <td style="font-weight:bold;">{mdbr:.1f}</td>
            </tr>
            """

        # --- ENSAMBLAJE HTML (HOJA VERTICAL) ---
        html_content = f"""
        <html><head><style>
            @page {{ size: A4 portrait; margin: 6mm; }}
            body {{ font-family: 'Arial', sans-serif; font-size: 5.5px; color: #000; line-height: 1.1; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 4px; border: 1px solid #000; table-layout: fixed; }}
            th, td {{ border: 1px solid #000; padding: 1.5px; text-align: center; word-wrap: break-word; overflow: hidden; }}
            .title-bar {{ font-size: 10px; font-weight: bold; text-align: center; margin-bottom: 3px; }}
            .nasa-blue {{ background-color: #0000cc; color: #fff; font-weight: bold; font-size: 6.5px; padding: 2px; }}
            .gray-header {{ background-color: #f0f0f0; font-weight: bold; font-size: 5px; }}
            .footer {{ font-size: 6px; font-style: italic; color: #333; margin-top: 5px; }}
        </style></head>
        <body>
            <div class="title-bar">POWER Climatic Design Conditions (Extracted via Advanced Model)</div>
            
            <table style="border:none; border-top:1.5px solid #000; border-bottom:1.5px solid #000; margin-bottom:4px; font-size: 6.5px;">
                <tr>
                    <td style="border:none; text-align:left;"><b>Latitude:</b> {format_coord(lat, True)}</td>
                    <td style="border:none; text-align:left;"><b>Longitude:</b> {format_coord(lon, False)}</td>
                    <td style="border:none; text-align:left;"><b>Elevation:</b> {alt_display}</td>
                    <td style="border:none; text-align:left;"><b>StdPres:</b> {calc_stdp(alt_display)}</td>
                    <td style="border:none; text-align:left;"><b>Time Zone:</b> -5.0</td>
                    <td style="border:none; text-align:left;"><b>Time Period:</b> {period_display}</td>
                </tr>
            </table>

            <table>
                <tr><th colspan="13" class="nasa-blue">Annual Heating and Humidification Design Conditions</th></tr>
                <tr class="gray-header">
                    <td rowspan="2">Coldest<br>Month</td>
                    <td colspan="2">Heating DB (°C)</td>
                    <td colspan="6">Humidification DP / HR / MCDB</td>
                    <td colspan="4">Coldest month WS / MCDB</td>
                </tr>
                <tr class="gray-header">
                    <td>99.6%</td><td>99%</td>
                    <td>99.6% DP</td><td>99.6% HR</td><td>99.6% MCDB</td>
                    <td>99% DP</td><td>99% HR</td><td>99% MCDB</td>
                    <td>0.4% WS</td><td>0.4% MCDB</td>
                    <td>1% WS</td><td>1% MCDB</td>
                </tr>
                <tr>
                    <td style="font-weight:bold;">{coldest_month}</td>
                    <td>{db_min_ann:.1f}</td><td>{df['DB'].quantile(0.010):.1f}</td>
                    <td>{df['DP'].quantile(0.004):.1f}</td><td>{mc(df, 'DP', 'HR', df['DP'].quantile(0.004)):.1f}</td><td>{mc(df, 'DP', 'DB', df['DP'].quantile(0.004)):.1f}</td>
                    <td>{df['DP'].quantile(0.010):.1f}</td><td>{mc(df, 'DP', 'HR', df['DP'].quantile(0.010)):.1f}</td><td>{mc(df, 'DP', 'DB', df['DP'].quantile(0.010)):.1f}</td>
                    <td>{df['WS'].quantile(0.996):.1f}</td><td>{mc(df, 'WS', 'DB', df['WS'].quantile(0.996)):.1f}</td>
                    <td>{df['WS'].quantile(0.990):.1f}</td><td>{mc(df, 'WS', 'DB', df['WS'].quantile(0.990)):.1f}</td>
                </tr>
            </table>

            <table>
                <tr><th colspan="14" class="nasa-blue">Annual Cooling, Dehumidification, and Enthalpy Design Conditions (Part 1)</th></tr>
                <tr class="gray-header">
                    <td rowspan="2">Hottest<br>Month</td>
                    <td rowspan="2">Month<br>DB Range</td>
                    <td colspan="6">Cooling DB / MCWB (°C)</td>
                    <td colspan="6">Evaporation WB / MCDB (°C)</td>
                </tr>
                <tr class="gray-header">
                    <td colspan="2">0.4%</td><td colspan="2">1%</td><td colspan="2">2%</td>
                    <td colspan="2">0.4%</td><td colspan="2">1%</td><td colspan="2">2%</td>
                </tr>
                <tr>
                    <td style="font-weight:bold;">{hottest_month}</td>
                    <td>{df[df['Month'] == hottest_month]['DB'].max() - df[df['Month'] == hottest_month]['DB'].min():.1f}</td>
                    <td>{db_max_ann:.1f}</td><td>{mc(df, 'DB', 'WB', db_max_ann):.1f}</td>
                    <td>{df['DB'].quantile(0.990):.1f}</td><td>{mc(df, 'DB', 'WB', df['DB'].quantile(0.990)):.1f}</td>
                    <td>{df['DB'].quantile(0.980):.1f}</td><td>{mc(df, 'DB', 'WB', df['DB'].quantile(0.980)):.1f}</td>
                    
                    <td>{wb_max_ann:.1f}</td><td>{mc(df, 'WB', 'DB', wb_max_ann):.1f}</td>
                    <td>{df['WB'].quantile(0.990):.1f}</td><td>{mc(df, 'WB', 'DB', df['WB'].quantile(0.990)):.1f}</td>
                    <td>{df['WB'].quantile(0.980):.1f}</td><td>{mc(df, 'WB', 'DB', df['WB'].quantile(0.980)):.1f}</td>
                </tr>
            </table>
            
            <table>
                <tr><th colspan="16" class="nasa-blue">Annual Cooling (Part 2) - Dehumidification & Enthalpy</th></tr>
                <tr class="gray-header">
                    <td colspan="9">Dehumidification DP / HR / MCDB</td>
                    <td colspan="6">Enthalpy / MCDB</td>
                    <td rowspan="2">Ext.<br>Max WB</td>
                </tr>
                <tr class="gray-header">
                    <td>0.4% DP</td><td>HR</td><td>MCDB</td>
                    <td>1% DP</td><td>HR</td><td>MCDB</td>
                    <td>2% DP</td><td>HR</td><td>MCDB</td>
                    <td>0.4% Enth</td><td>MCDB</td>
                    <td>1% Enth</td><td>MCDB</td>
                    <td>2% Enth</td><td>MCDB</td>
                </tr>
                <tr>
                    <td>{dp_max_ann:.1f}</td><td>{mc(df, 'DP', 'HR', dp_max_ann):.1f}</td><td>{mc(df, 'DP', 'DB', dp_max_ann):.1f}</td>
                    <td>{df['DP'].quantile(0.990):.1f}</td><td>{mc(df, 'DP', 'HR', df['DP'].quantile(0.990)):.1f}</td><td>{mc(df, 'DP', 'DB', df['DP'].quantile(0.990)):.1f}</td>
                    <td>{df['DP'].quantile(0.980):.1f}</td><td>{mc(df, 'DP', 'HR', df['DP'].quantile(0.980)):.1f}</td><td>{mc(df, 'DP', 'DB', df['DP'].quantile(0.980)):.1f}</td>
                    
                    <td>{enth_max_ann:.1f}</td><td>{mc(df, 'Enth', 'DB', enth_max_ann):.1f}</td>
                    <td>{df['Enth'].quantile(0.990):.1f}</td><td>{mc(df, 'Enth', 'DB', df['Enth'].quantile(0.990)):.1f}</td>
                    <td>{df['Enth'].quantile(0.980):.1f}</td><td>{mc(df, 'Enth', 'DB', df['Enth'].quantile(0.980)):.1f}</td>
                    <td style="font-weight:bold;">{df['WB'].max():.1f}</td>
                </tr>
            </table>

            <table>
                <tr><th colspan="11" class="nasa-blue">Extreme Annual Design Conditions (Return Periods Calculated via NASA Matrix)</th></tr>
                <tr class="gray-header">
                    <td colspan="3">Extreme Annual WS (m/s)</td>
                    <td colspan="4">Extreme Annual Temp (Mean Min/Max & Std)</td>
                    <td colspan="4">n-Year Return Period Values of Extreme Temp (°C)</td>
                </tr>
                <tr class="gray-header">
                    <td>1%</td><td>2.5%</td><td>5%</td>
                    <td>DB Mean Min/Max</td><td>DB Std</td><td>WB Mean Min/Max</td><td>WB Std</td>
                    <td>n = 5 years</td><td>n = 10 years</td><td>n = 20 years</td><td>n = 50 years</td>
                </tr>
                <tr>
                    <td>{df['WS'].quantile(0.990):.1f}</td><td>{df['WS'].quantile(0.975):.1f}</td><td>{df['WS'].quantile(0.950):.1f}</td>
                    <td>{ann_min_db.mean():.1f} / {ann_max_db.mean():.1f}</td><td>{ann_max_db.std():.1f}</td>
                    <td>{ann_min_wb.mean():.1f} / {ann_max_wb.mean():.1f}</td><td>{ann_max_wb.std():.1f}</td>
                    <td>{get_rp_min(ann_min_db, 5):.1f} / {get_rp_max(ann_max_db, 5):.1f}</td>
                    <td>{get_rp_min(ann_min_db, 10):.1f} / {get_rp_max(ann_max_db, 10):.1f}</td>
                    <td>{get_rp_min(ann_min_db, 20):.1f} / {get_rp_max(ann_max_db, 20):.1f}</td>
                    <td>{get_rp_min(ann_min_db, 50):.1f} / {get_rp_max(ann_max_db, 50):.1f}</td>
                </tr>
            </table>

            <table>
                <tr><th colspan="27" class="nasa-blue">Monthly Climatic Design Conditions</th></tr>
                <tr class="gray-header">
                    <td rowspan="2">Mth</td>
                    <td colspan="9">Temperatures, Degree-Days and Wind</td>
                    <td colspan="8" style="background-color: #d1e2f3;">Monthly Design Dry Bulb / MCWB (°C)</td>
                    <td colspan="8" style="background-color: #ffe6cc;">Monthly Design Wet Bulb / MCDB (°C)</td>
                    <td rowspan="2">MDBR</td>
                </tr>
                <tr class="gray-header">
                    <td>DBAvg</td><td>DBStd</td>
                    <td>HD10</td><td>HD18</td><td>CD10</td><td>CD18</td><td>CH23</td><td>CH26</td>
                    <td>WSAvg</td>
                    
                    <td colspan="2" style="background-color: #d1e2f3;">0.4%</td><td colspan="2" style="background-color: #d1e2f3;">2%</td>
                    <td colspan="2" style="background-color: #d1e2f3;">5%</td><td colspan="2" style="background-color: #d1e2f3;">10%</td>
                    
                    <td colspan="2" style="background-color: #ffe6cc;">0.4%</td><td colspan="2" style="background-color: #ffe6cc;">2%</td>
                    <td colspan="2" style="background-color: #ffe6cc;">5%</td><td colspan="2" style="background-color: #ffe6cc;">10%</td>
                </tr>
                {m_rows}
            </table>
            
            <div class="footer">
                <b>{fuente}</b> | Este reporte emplea formulación psicrométrica avanzada para derivar HR (Ratio de Humedad) y Entalpía desde la presión de vapor, 
                así como análisis de frecuencia para Periodos de Retorno Extremos empíricos. Formato de renderizado A4-Vertical.
            </div>
        </body></html>"""
        
        pdf_file = HTML(string=html_content).write_pdf()
        st.success("¡Matriz Completa Estilo NASA generada exitosamente en formato Vertical!")
        st.download_button("📥 Descargar Reporte NASA Vertical", data=pdf_file, file_name=f"NASA_Matrix_Vertical_{city_display.replace(' - ', '_')}.pdf", mime="application/pdf")
