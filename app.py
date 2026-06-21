import streamlit as st
import pandas as pd
import numpy as np
import requests
import os
from weasyprint import HTML

st.set_page_config(page_title="Generador de Reportes Climáticos", layout="wide")
st.title("🌍 Generador de Reportes: Condiciones Climáticas de Diseño (Estilo NASA POWER)")

# --- 1. FUNCIONES BASE Y DE GEOLOCALIZACIÓN ---
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

def format_coord(val, is_lat):
    try: return f"{abs(float(val)):.4f}{'N' if float(val) >= 0 else 'S'}" if is_lat else f"{abs(float(val)):.4f}{'E' if float(val) >= 0 else 'W'}"
    except: return str(val)

def get_epw_mapping():
    if not os.path.exists("data"): return {}
    return {clean_city_name(f): f for f in sorted([f for f in os.listdir("data") if f.endswith(".epw")])}

# --- 2. MOTOR PSICROMÉTRICO Y COINCIDENTE ---
def calc_wb(T, RH):
    # Aproximación de Stull
    return T * np.arctan(0.151977 * (RH + 8.313659)**0.5) + np.arctan(T + RH) - np.arctan(RH - 1.676331) + 0.00391838 * (RH)**1.5 * np.arctan(0.023101 * RH) - 4.686035

def calc_enthalpy(T, HR):
    # Entalpía en kJ/kg
    return 1.006 * T + (HR/1000) * (2501 + 1.86 * T)

def mc(sub, base_col, target_col, t):
    h = sub[(sub[base_col] >= t - 0.2) & (sub[base_col] <= t + 0.2)]
    return h[target_col].mean() if not h.empty else sub[target_col].mean()

# --- 3. INTERFAZ STREAMLIT ---
modo = st.radio("Método de Generación (Formato Oficial NASA POWER Vertical):", ["🏢 Estación Local (Archivos EPW)", "📍 Coordenadas (NASA Satelital 24 Años)"], horizontal=True)
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
    col1.info("📅 Rango Satelital Fijado: 2001 - 2024")
    lat = col2.number_input("Latitud", value=-9.5653, format="%.4f")
    lon = col3.number_input("Longitud", value=-77.0364, format="%.4f")

st.markdown("<br>", unsafe_allow_html=True) 

if st.button("Generar Reporte NASA (A4 Vertical)"):
    with st.spinner("Procesando matriz histórica y construyendo renderizado vertical (Puede tardar ~40 segundos)..."):
        
        # --- 4. EXTRACCIÓN DE DATOS ---
        if usar_local:
            filename = file_map[selected_city]
            city_display, period_display = selected_city.upper(), "TMYx"
            try:
                for p in filename.replace(".epw", "").split('.'):
                    if "-" in p and len(p) == 9 and p.split('-')[0].isdigit(): period_display = p
                with open(f"data/{filename}", 'r', encoding='utf-8') as f:
                    h_data = f.readline().split(',')
                    lat_val, lon_val, alt_display = float(h_data[6]), float(h_data[7]), float(h_data[9].strip())
            except: lat_val, lon_val, alt_display = 0, 0, 0

            # DB(6), DP(7), RH(8), Press(9), GHR(13), DirNorm(14), WS(21), Precip(33)
            df = pd.read_csv(f"data/{filename}", skiprows=8, header=None, usecols=[1,2,6,7,8,9,13,14,21,33], names=['Month','Day','DB','DP','RH','Press','RadAvg','RadClr','WS','Precip'])
            df['Press_kPa'] = df['Press'] / 1000
            df['Precip'] = pd.to_numeric(df['Precip'], errors='coerce').fillna(0)
            df['Precip'] = df['Precip'].apply(lambda x: 0 if x > 900 else x)
            df['Year'] = 2024
            lat, lon = lat_val, lon_val
            fuente = f"Data: Local EPW. {len(df)} horas."

        else:
            city_display, period_display = get_location_name(lat, lon).upper(), "2001 - 2024"
            dfs = []
            for y in range(2001, 2025):
                url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET,T2MDEW,WS10M,PS,PRECTOTCORR,ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN&community=SB&longitude={lon}&latitude={lat}&start={y}0101&end={y}1231&format=JSON"
                try:
                    res = requests.get(url, timeout=20).json()
                    if y == 2001 and 'geometry' in res: alt_display = float(res['geometry']['coordinates'][2])
                    props = res['properties']['parameter']
                    t_df = pd.DataFrame({
                        'DB': list(props['T2M'].values()), 'WB': list(props['T2MWET'].values()), 'DP': list(props['T2MDEW'].values()),
                        'WS': list(props['WS10M'].values()), 'Press_kPa': list(props['PS'].values()), 'Precip': list(props['PRECTOTCORR'].values()),
                        'RadAvg': list(props['ALLSKY_SFC_SW_DWN'].values()), 'RadClr': list(props['CLRSKY_SFC_SW_DWN'].values())
                    })
                    t_df['Month'] = pd.date_range(start=f"{y}-01-01", periods=len(t_df), freq='h').month
                    t_df['Year'] = y
                    dfs.append(t_df)
                except: continue
            df = pd.concat(dfs, ignore_index=True)
            fuente = f"Data: NASA POWER API ({period_display}). {len(df):,} horas."

        # --- 5. TERMODINÁMICA ---
        df['Pv'] = 0.61078 * np.exp(17.27 * df['DP'] / (df['DP'] + 237.3))
        df['HR'] = 1000 * 0.62198 * df['Pv'] / (df['Press_kPa'] - df['Pv']) 
        df['Enth'] = calc_enthalpy(df['DB'], df['HR'])
        if usar_local: df['WB'] = calc_wb(df['DB'], df['RH'])

        years_count = len(df['Year'].unique()) if len(df['Year'].unique()) > 0 else 1
        stdp_display = f"{101.325 * (1 - 2.25577e-5 * alt_display)**5.25588:.2f}"

        # --- 6. EXTREMOS Y PERIODOS DE RETORNO ---
        db_max_ann, db_min_ann = df['DB'].quantile(0.996), df['DB'].quantile(0.004)
        wb_max_ann, dp_max_ann = df['WB'].quantile(0.996), df['DP'].quantile(0.996)
        hottest_month = df.groupby('Month')['DB'].mean().idxmax()
        coldest_month = df.groupby('Month')['DB'].mean().idxmin()

        ann_min_db = df.groupby('Year')['DB'].min()
        ann_max_db = df.groupby('Year')['DB'].max()
        ann_min_wb = df.groupby('Year')['WB'].min()
        ann_max_wb = df.groupby('Year')['WB'].max()

        def rp(s, t, is_max=True): return s.quantile(1 - 1/t) if is_max and len(s)>10 else (s.quantile(1/t) if len(s)>10 else (s.max() if is_max else s.min()))

        # --- 7. MATRIZ MENSUAL (TRANSFORMADA A COLUMNAS) ---
        cols = [df] + [df[df['Month'] == m] for m in range(1, 13)]
        
        def build_row(title, rowspan, subtitle, sub2, func):
            vals = [func(c) if not c.empty else 0 for c in cols]
            row_html = f"<tr>"
            if title: row_html += f"<td rowspan='{rowspan}' style='font-weight:bold; background:#fff; text-align:center;'>{title}</td>"
            if subtitle: row_html += f"<td style='background:#fff; text-align:center;'>{subtitle}</td>"
            if sub2: row_html += f"<td style='background:#fff; text-align:center;'>{sub2}</td>"
            for v in vals: row_html += f"<td style='background:#fff;'>{v:.1f}</td>" if isinstance(v, float) else f"<td style='background:#fff;'>{v}</td>"
            row_html += "</tr>"
            return row_html

        # Diccionarios de Funciones Lambda
        f_dbavg = lambda x: x['DB'].mean()
        f_dbstd = lambda x: x['DB'].std()
        f_hdd10 = lambda x: (10.0 - x['DB']).clip(lower=0).sum() / 24 / years_count
        f_hdd18 = lambda x: (18.3 - x['DB']).clip(lower=0).sum() / 24 / years_count
        f_cdd10 = lambda x: (x['DB'] - 10.0).clip(lower=0).sum() / 24 / years_count
        f_cdd18 = lambda x: (x['DB'] - 18.3).clip(lower=0).sum() / 24 / years_count
        f_cdh23 = lambda x: (x['DB'] - 23.3).clip(lower=0).sum() / years_count
        f_cdh26 = lambda x: (x['DB'] - 26.7).clip(lower=0).sum() / years_count
        
        f_wsavg = lambda x: x['WS'].mean()
        
        f_precavg = lambda x: x['Precip'].sum() / years_count
        f_precmax = lambda x: x.groupby(['Year', x.index//(730 if len(x)>8760 else 8760)])['Precip'].sum().max()
        f_precmin = lambda x: x.groupby(['Year', x.index//(730 if len(x)>8760 else 8760)])['Precip'].sum().min()
        f_precstd = lambda x: x.groupby(['Year', x.index//(730 if len(x)>8760 else 8760)])['Precip'].sum().std()

        f_db04 = lambda x: x['DB'].quantile(0.996)
        f_mcwb04 = lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.996))
        f_db20 = lambda x: x['DB'].quantile(0.980)
        f_mcwb20 = lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.980))
        f_db50 = lambda x: x['DB'].quantile(0.950)
        f_mcwb50 = lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.950))
        f_db10 = lambda x: x['DB'].quantile(0.900)
        f_mcwb10 = lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.900))

        f_wb04 = lambda x: x['WB'].quantile(0.996)
        f_mcdb04 = lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.996))
        f_wb20 = lambda x: x['WB'].quantile(0.980)
        f_mcdb20 = lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.980))
        f_wb50 = lambda x: x['WB'].quantile(0.950)
        f_mcdb50 = lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.950))
        f_wb10 = lambda x: x['WB'].quantile(0.900)
        f_mcdb10 = lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.900))

        f_mdbr = lambda x: (x.groupby([x['Year'], x.index // 24])['DB'].max() - x.groupby([x['Year'], x.index // 24])['DB'].min()).mean()
        
        f_radavg = lambda x: x['RadAvg'].mean() * 24 / 1000 if not usar_local else x['RadAvg'].mean() / 1000
        f_radclr = lambda x: x['RadClr'].mean() * 24 / 1000 if not usar_local else x['RadClr'].mean() / 1000

        # Construyendo HTML filas dinámicas
        matrix_html = build_row("Temperatures,<br>Degree-Days<br>and<br>Degree-Hours<br>(°C)", 8, "DBAvg", "", f_dbavg)
        matrix_html += build_row(None, 0, "DBStd", "", f_dbstd)
        matrix_html += build_row(None, 0, "HDD10.0", "", f_hdd10)
        matrix_html += build_row(None, 0, "HDD18.3", "", f_hdd18)
        matrix_html += build_row(None, 0, "CDD10.0", "", f_cdd10)
        matrix_html += build_row(None, 0, "CDD18.3", "", f_cdd18)
        matrix_html += build_row(None, 0, "CDH23.3", "", f_cdh23)
        matrix_html += build_row(None, 0, "CDH26.7", "", f_cdh26)
        
        matrix_html += build_row("Wind (m/s)", 1, "WSAvg", "", f_wsavg)
        
        matrix_html += build_row("Precipitation<br>(mm)", 4, "PrecAvg", "", f_precavg)
        matrix_html += build_row(None, 0, "PrecMax", "", f_precmax)
        matrix_html += build_row(None, 0, "PrecMin", "", f_precmin)
        matrix_html += build_row(None, 0, "PrecStd", "", lambda x: f_precstd(x) if pd.notna(f_precstd(x)) else 0)

        matrix_html += build_row("Monthly Design<br>Dry Bulb and<br>MCWB<br>(°C)", 8, "0.4%", "DB", f_db04)
        matrix_html += build_row(None, 0, "", "MCWB", f_mcwb04)
        matrix_html += build_row(None, 0, "2%", "DB", f_db20)
        matrix_html += build_row(None, 0, "", "MCWB", f_mcwb20)
        matrix_html += build_row(None, 0, "5%", "DB", f_db50)
        matrix_html += build_row(None, 0, "", "MCWB", f_mcwb50)
        matrix_html += build_row(None, 0, "10%", "DB", f_db10)
        matrix_html += build_row(None, 0, "", "MCWB", f_mcwb10)

        matrix_html += build_row("Monthly Design<br>Wet Bulb and<br>MCDB<br>(°C)", 8, "0.4%", "WB", f_wb04)
        matrix_html += build_row(None, 0, "", "MCDB", f_mcdb04)
        matrix_html += build_row(None, 0, "2%", "WB", f_wb20)
        matrix_html += build_row(None, 0, "", "MCDB", f_mcdb20)
        matrix_html += build_row(None, 0, "5%", "WB", f_wb50)
        matrix_html += build_row(None, 0, "", "MCDB", f_mcdb50)
        matrix_html += build_row(None, 0, "10%", "WB", f_wb10)
        matrix_html += build_row(None, 0, "", "MCDB", f_mcdb10)

        matrix_html += build_row("Mean Daily<br>Temp Range", 1, "MDBR", "", f_mdbr)
        
        matrix_html += build_row("Clear Sky Solar<br>(kWh m-2)", 1, "RadClr", "", f_radclr)
        matrix_html += build_row("All-Sky Solar<br>(kWh m-2)", 1, "RadAvg", "", f_radavg)

        # --- 8. RENDERIZADO HTML/CSS EXACTO (PORTRAIT A4) ---
        html_content = f"""
        <html><head><style>
            @page {{ size: A4 portrait; margin: 8mm; }}
            body {{ font-family: 'Times New Roman', serif; font-size: 7px; color: #000; line-height: 1.1; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 5px; border: 1.5px solid #000; table-layout: fixed; }}
            th, td {{ border: 1px solid #000; padding: 2px; text-align: center; overflow: hidden; }}
            .nasa-blue {{ background-color: #0000cc; color: #fff; font-weight: bold; font-size: 8px; padding: 3px; }}
            .gray-header {{ background-color: #f2f2f2; font-weight: bold; }}
            .title-bar {{ font-size: 11px; font-weight: bold; text-align: center; margin-bottom: 4px; }}
            .footer {{ font-size: 7px; font-style: italic; margin-top: 10px; color: #333; }}
        </style></head>
        <body>
            <div class="title-bar">POWER Climatic Design Conditions (GMAO MERRA-2 and CERES SYN1deg)</div>
            
            <table style="border:none; border-top:1.5px solid #000; border-bottom:1.5px solid #000; margin-bottom:5px;">
                <tr>
                    <td style="border:none; text-align:left;"><b>Latitude:</b> {format_coord(lat, True)}</td>
                    <td style="border:none; text-align:left;"><b>Longitude:</b> {format_coord(lon, False)}</td>
                    <td style="border:none; text-align:left;"><b>Elevation:</b> {alt_display}</td>
                    <td style="border:none; text-align:left;"><b>StdPres:</b> {stdp_display}</td>
                    <td style="border:none; text-align:left;"><b>Time Zone:</b> -5.0</td>
                    <td style="border:none; text-align:left;"><b>Time Period:</b> {period_display}</td>
                </tr>
            </table>

            <table>
                <tr><th colspan="12" class="nasa-blue">Annual Heating and Humidification Design Conditions</th></tr>
                <tr class="gray-header">
                    <td rowspan="2">Coldest<br>Month</td>
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
                <tr><th colspan="16" class="nasa-blue">Annual Cooling, Dehumidification, and Enthalpy Design Conditions</th></tr>
                <tr class="gray-header">
                    <td rowspan="2">Hottest<br>Month</td>
                    <td rowspan="2">DB<br>Range</td>
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
                    
                    <td>{df['Enth'].quantile(0.996):.1f}</td><td>{df['Enth'].quantile(0.990):.1f}</td><td>{mc(df, 'Enth', 'DB', df['Enth'].quantile(0.996)):.1f}</td>
                </tr>
            </table>

            <table>
                <tr><th colspan="12" class="nasa-blue">Extreme Annual Design Conditions</th></tr>
                <tr class="gray-header">
                    <td colspan="3">Extreme Annual WS (m/s)</td>
                    <td colspan="5">Extreme Annual Temperature (°C)</td>
                    <td colspan="4">n-Year Return Period Values of Extreme Temp (°C)</td>
                </tr>
                <tr class="gray-header">
                    <td>1%</td><td>2.5%</td><td>5%</td>
                    <td>DB Mean Min/Max</td><td>Std Dev</td><td>WB Mean Min/Max</td><td>Std Dev</td><td></td>
                    <td>n=5 years</td><td>n=10 years</td><td>n=20 years</td><td>n=50 years</td>
                </tr>
                <tr>
                    <td rowspan="2">{df['WS'].quantile(0.990):.1f}</td><td rowspan="2">{df['WS'].quantile(0.975):.1f}</td><td rowspan="2">{df['WS'].quantile(0.950):.1f}</td>
                    <td>DB</td><td>{ann_min_db.mean():.1f} / {ann_max_db.mean():.1f}</td><td>{ann_min_db.std():.1f} / {ann_max_db.std():.1f}</td><td>WB</td><td>{ann_min_wb.mean():.1f} / {ann_max_wb.mean():.1f}</td>
                    <td>Min/Max</td>
                    <td>{rp(ann_min_db, 5, False):.1f} / {rp(ann_max_db, 5):.1f}</td>
                    <td>{rp(ann_min_db, 10, False):.1f} / {rp(ann_max_db, 10):.1f}</td>
                    <td>{rp(ann_min_db, 20, False):.1f} / {rp(ann_max_db, 20):.1f}</td>
                    <td>{rp(ann_min_db, 50, False):.1f} / {rp(ann_max_db, 50):.1f}</td>
                </tr>
            </table>

            <table>
                <tr><th colspan="16" class="nasa-blue">Monthly Climatic Design Conditions</th></tr>
                <tr class="gray-header">
                    <td colspan="3">Parameters</td>
                    <td>Annual</td>
                    <td>Jan</td><td>Feb</td><td>Mar</td><td>Apr</td><td>May</td><td>Jun</td>
                    <td>Jul</td><td>Aug</td><td>Sep</td><td>Oct</td><td>Nov</td><td>Dec</td>
                </tr>
                {matrix_html}
            </table>
            
            <div class="footer">
                {fuente} | La tabla mensual se renderizó transpuesta (columnas = meses) y ajustada milimétricamente en CSS (font-size: 7px, table-layout: fixed) para garantizar 
                el encaje perfecto en formato Vertical A4, replicando estrictamente el layout de la NASA POWER.
            </div>
        </body></html>"""
        
        pdf_file = HTML(string=html_content).write_pdf()
        st.success("¡Súper Matriz generada exitosamente en formato Vertical!")
        st.download_button("📥 Descargar Reporte NASA Vertical", data=pdf_file, file_name=f"NASA_Matrix_Vertical_{city_display.replace(' - ', '_')}.pdf", mime="application/pdf")
