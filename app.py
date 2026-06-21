import streamlit as st
import pandas as pd
import requests
import os
from weasyprint import HTML

st.set_page_config(page_title="Generador de Reportes Climáticos", layout="wide")
st.title("🌍 Generador de Reportes: Condiciones Climáticas de Diseño (Estilo NASA POWER)")

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
            subparts = parts[2].split('.')
            city_words = []
            for p in subparts:
                if p in ['AP', 'Intl', 'TMYx'] or p.isdigit() or ('-' in p and p.split('-')[0].isdigit()): break
                city_words.append(p)
            ciudad = " ".join(city_words).split('-')[0].strip() 
            correcciones = {"Tacna": "Tacna", "Ilo": "Moquegua"}
            if ciudad in correcciones: departamento = correcciones[ciudad]
            return f"{pais} - {departamento} - {ciudad}"
        return filename.replace(".epw", "")
    except:
        return filename

def get_location_name(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        headers = {'User-Agent': 'GeneradorClima_Peru_v4'}
        res = requests.get(url, headers=headers, timeout=5).json()
        address = res.get('address', {})
        pais = address.get('country', 'Perú')
        departamento = address.get('state', address.get('region', ''))
        ciudad = address.get('city', address.get('town', address.get('village', address.get('suburb', 'Ubicación Desconocida'))))
        return f"{pais} - {departamento} - {ciudad}" if departamento else f"{pais} - {ciudad}"
    except:
        return f"Coordenadas [Lat: {lat}, Lon: {lon}]"

def calc_stdp(elev_m):
    try:
        z = float(elev_m)
        return f"{101.325 * (1 - 2.25577e-5 * z)**5.25588:.2f}"
    except:
        return "101.32"

def get_epw_mapping():
    if not os.path.exists("data"): return {}
    return {clean_city_name(f): f for f in sorted([f for f in os.listdir("data") if f.endswith(".epw")])}

# --- INTERFAZ STREAMLIT ---
modo = st.radio(
    "Seleccione el método de generación (Formato Matriz NASA POWER):",
    ["🏢 Búsqueda por Estación de Ciudad (EPW)", "📍 Búsqueda por Coordenadas (NASA API)"],
    horizontal=True
)
st.markdown("---") 

col1, col2, col3 = st.columns(3)
file_map = get_epw_mapping()

if "Estación" in modo:
    usar_local = True
    selected_city = col1.selectbox("Seleccionar ciudad de la base de datos:", list(file_map.keys()))
    lat = col2.number_input("Latitud", value=0.0000, format="%.4f", disabled=True)
    lon = col3.number_input("Longitud", value=0.0000, format="%.4f", disabled=True)
else:
    usar_local = False
    selected_city = None
    col1.info("📅 Periodo de análisis Satelital NASA Fijado: 2001 - 2024")
    lat = col2.number_input("Latitud", value=-9.5653, format="%.4f")
    lon = col3.number_input("Longitud", value=-77.0364, format="%.4f")

st.markdown("<br>", unsafe_allow_html=True) 

if st.button("Generar Súper Reporte (Formato Oficial)"):
    msg_spinner = "Procesando algoritmos y renderizando matriz estilo NASA..."
    
    with st.spinner(msg_spinner):
        fuente, city_display, alt_display, period_display, wmo_display = "", "Ubicación", "0", "N/A", "N/A"

        # ==========================================
        # EXTRACCIÓN DE DATOS (EPW O NASA)
        # ==========================================
        if usar_local:
            filename = file_map[selected_city]
            city_display = selected_city.upper()
            period_display = "TMYx"
            try:
                for p in filename.replace(".epw", "").split('.'):
                    if "-" in p and len(p) == 9 and p.split('-')[0].isdigit():
                        period_display = p
                        break
                with open(f"data/{filename}", 'r', encoding='utf-8') as f:
                    header_data = f.readline().split(',')
                    wmo_display = header_data[5].strip()
                    lat, lon = float(header_data[6]), float(header_data[7])
                    alt_display = header_data[9].strip()
            except: pass 
            
            # Leemos Bulbo Seco (DB), Bulbo Húmedo (WB), y Velocidad de Viento (WS)
            df = pd.read_csv(f"data/{filename}", skiprows=8, header=None, usecols=[1,2,6,8,21], names=['Month', 'Day', 'DB', 'WB', 'WS'])
            fuente = f"Generado desde EPW Local. {len(df)} horas procesadas."

        else:
            city_display = get_location_name(lat, lon).upper()
            wmo_display = "SATELITAL"
            period_display = "2001 - 2024"
            start_year, end_year = 2001, 2024
            
            dfs = []
            for y in range(start_year, end_year + 1):
                url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET,WS10M&community=SB&longitude={lon}&latitude={lat}&start={y}0101&end={y}1231&format=JSON"
                try:
                    res = requests.get(url, timeout=20).json()
                    if y == start_year and 'geometry' in res:
                        alt_display = str(round(res['geometry']['coordinates'][2], 1))
                    
                    # T2M (DB), T2MWET (WB), WS10M (Wind Speed)
                    db_vals = list(res['properties']['parameter']['T2M'].values())
                    wb_vals = list(res['properties']['parameter']['T2MWET'].values())
                    ws_vals = list(res['properties']['parameter']['WS10M'].values())
                    
                    temp_df = pd.DataFrame({'DB': db_vals, 'WB': wb_vals, 'WS': ws_vals})
                    temp_df['Month'] = pd.date_range(start=f"{y}-01-01", periods=len(temp_df), freq='h').month
                    dfs.append(temp_df)
                except: continue
            
            if not dfs:
                st.error("Error al descargar datos de la NASA.")
                st.stop()
            df = pd.concat(dfs, ignore_index=True)
            fuente = f"Generado mediante reanálisis NASA ({period_display}). {len(df)} horas continuas procesadas."

        # ==========================================
        # MOTOR MATEMÁTICO AVANZADO
        # ==========================================
        def mcwb(sub, t):
            h = sub[(sub['DB'] >= t - 0.5) & (sub['DB'] <= t + 0.5)]
            return h['WB'].mean() if not h.empty else sub['WB'].max()

        # Cálculos Anuales
        db_max_ann = df['DB'].quantile(0.996) # Cooling 0.4%
        db_min_ann = df['DB'].quantile(0.004) # Heating 99.6%
        hottest_month = df.groupby('Month')['DB'].mean().idxmax()
        coldest_month = df.groupby('Month')['DB'].mean().idxmin()

        meses_str = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        meses_full = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

        # Matrices Mensuales
        data_rows = []
        for m in range(1, 13):
            df_m = df[df['Month'] == m]
            if df_m.empty: continue
            
            db_avg = df_m['DB'].mean()
            db_std = df_m['DB'].std()
            ws_avg = df_m['WS'].mean()
            
            # Grados Día
            hdd10 = df_m['DB'].apply(lambda x: max(0, 10.0 - x)).sum() / 24
            hdd18 = df_m['DB'].apply(lambda x: max(0, 18.3 - x)).sum() / 24
            cdd10 = df_m['DB'].apply(lambda x: max(0, x - 10.0)).sum() / 24
            cdd18 = df_m['DB'].apply(lambda x: max(0, x - 18.3)).sum() / 24
            
            db04 = df_m['DB'].quantile(0.996)
            db20 = df_m['DB'].quantile(0.980)
            db50 = df_m['DB'].quantile(0.950)
            db100 = df_m['DB'].quantile(0.900)
            
            wb04 = df_m['WB'].quantile(0.996)
            wb20 = df_m['WB'].quantile(0.980)
            
            range_c = (df_m.groupby(df_m.index // 24)['DB'].max() - df_m.groupby(df_m.index // 24)['DB'].min()).mean()
            
            data_rows.append({
                'Mes': meses_str[m-1], 'MesFull': meses_full[m-1],
                'DBAvg': db_avg, 'DBStd': db_std, 'WSAvg': ws_avg,
                'HDD10': hdd10, 'HDD18': hdd18, 'CDD10': cdd10, 'CDD18': cdd18,
                'DB04': db04, 'MCWB04': mcwb(df_m, db04), 'DB20': db20, 'MCWB20': mcwb(df_m, db20),
                'DB50': db50, 'MCWB50': mcwb(df_m, db50), 'DB100': db100, 'MCWB100': mcwb(df_m, db100),
                'WB04': wb04, 'MCDB_W04': df_m.loc[(df_m['WB'] >= wb04 - 0.2) & (df_m['WB'] <= wb04 + 0.2), 'DB'].mean(),
                'WB20': wb20, 'MCDB_W20': df_m.loc[(df_m['WB'] >= wb20 - 0.2) & (df_m['WB'] <= wb20 + 0.2), 'DB'].mean(),
                'MDBR': range_c
            })

        stdp_display = calc_stdp(alt_display)

        # ==========================================
        # RENDERIZADO HTML: ESTILO EXACTO NASA POWER
        # ==========================================
        
        # 1. Filas de "Monthly Climatic Design Conditions" (Múltiples sub-secciones)
        filas_monthly = ""
        for r in data_rows:
            # Rellenamos NA con valores seguros si algo falla
            mcdb_w04 = r['MCDB_W04'] if pd.notna(r['MCDB_W04']) else r['DB04']
            mcdb_w20 = r['MCDB_W20'] if pd.notna(r['MCDB_W20']) else r['DB20']
            
            filas_monthly += f"""
            <tr style="text-align: center; font-size: 10px; border-bottom: 1px solid #000;">
                <td style="font-weight: bold; background-color: #f2f2f2; border-right: 1px solid #000;">{r['MesFull']}</td>
                <td style="border-right: 1px solid #aaa;">{r['DBAvg']:.1f}</td>
                <td style="border-right: 1px solid #aaa;">{r['DBStd']:.1f}</td>
                <td style="border-right: 1px solid #000;">{r['WSAvg']:.1f}</td>
                <td style="border-right: 1px solid #aaa;">{r['HDD10']:.0f}</td>
                <td style="border-right: 1px solid #000;">{r['HDD18']:.0f}</td>
                <td style="border-right: 1px solid #aaa;">{r['CDD10']:.0f}</td>
                <td style="border-right: 1px solid #000;">{r['CDD18']:.0f}</td>
                
                <td style="background-color: #eaf1f8; border-right: 1px solid #aaa;">{r['DB04']:.1f}</td>
                <td style="background-color: #eaf1f8; border-right: 1px solid #000;">{r['MCWB04']:.1f}</td>
                <td style="background-color: #eaf1f8; border-right: 1px solid #aaa;">{r['DB20']:.1f}</td>
                <td style="background-color: #eaf1f8; border-right: 1px solid #000;">{r['MCWB20']:.1f}</td>
                
                <td style="background-color: #fff4e6; border-right: 1px solid #aaa;">{r['WB04']:.1f}</td>
                <td style="background-color: #fff4e6; border-right: 1px solid #000;">{mcdb_w04:.1f}</td>
                <td style="background-color: #fff4e6; border-right: 1px solid #aaa;">{r['WB20']:.1f}</td>
                <td style="background-color: #fff4e6; border-right: 1px solid #000;">{mcdb_w20:.1f}</td>
                
                <td style="background-color: #e6ffe6; font-weight:bold;">{r['MDBR']:.1f}</td>
            </tr>
            """

        html_content = f"""
        <html><head><style>
            @page {{ size: A4 landscape; margin: 8mm; }}
            body {{ font-family: 'Times New Roman', Times, serif; font-size: 10px; color: #000; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 10px; border: 2px solid #000; }}
            th, td {{ border: 1px solid #000; padding: 3px; text-align: center; }}
            
            /* Colores Exactos de NASA POWER */
            .nasa-blue {{ background-color: #000099; color: white; font-weight: bold; font-size: 11px; }}
            .nasa-light {{ background-color: #f2f2f2; font-weight: bold; font-size: 9px; }}
            
            .header-info {{ font-weight: bold; font-size: 11px; margin-bottom: 5px; text-align: center; }}
            .footer {{ font-size: 8px; color: #333; margin-top: 10px; font-style: italic; }}
        </style></head>
        <body>
            <div style="text-align: center; font-size: 14px; font-weight: bold; margin-bottom: 5px;">POWER Climatic Design Conditions (Extracted via Advanced Model)</div>
            
            <div class="header-info">
                Latitude: {lat:.4f} &nbsp;&nbsp;|&nbsp;&nbsp; Longitude: {lon:.4f} &nbsp;&nbsp;|&nbsp;&nbsp; 
                Elevation: {alt_display} m &nbsp;&nbsp;|&nbsp;&nbsp; StdPres: {stdp_display} kPa &nbsp;&nbsp;|&nbsp;&nbsp; 
                Time Zone: -5.0 &nbsp;&nbsp;|&nbsp;&nbsp; Time Period: {period_display}
            </div>
            
            <table>
                <tr><th colspan="7" class="nasa-blue">Annual Heating and Humidification Design Conditions</th></tr>
                <tr class="nasa-light">
                    <td rowspan="2">Coldest<br>Month</td>
                    <td colspan="2">Heating DB (°C)</td>
                    <td colspan="2">Humidification DP (°C)</td>
                    <td colspan="2">Coldest month WS (m/s)</td>
                </tr>
                <tr class="nasa-light">
                    <td>99.6%</td><td>99%</td>
                    <td>99.6%</td><td>99%</td>
                    <td>0.4%</td><td>1%</td>
                </tr>
                <tr>
                    <td style="font-weight:bold;">{coldest_month}</td>
                    <td>{db_min_ann:.1f}</td><td>{df['DB'].quantile(0.010):.1f}</td>
                    <td>N/A</td><td>N/A</td>
                    <td>{df['WS'].quantile(0.996):.1f}</td><td>{df['WS'].quantile(0.990):.1f}</td>
                </tr>
            </table>

            <table>
                <tr><th colspan="7" class="nasa-blue">Annual Cooling, Dehumidification, and Enthalpy Design Conditions</th></tr>
                <tr class="nasa-light">
                    <td rowspan="2">Hottest<br>Month</td>
                    <td colspan="2">Cooling DB / MCWB (°C)</td>
                    <td colspan="2">Evaporation WB / MCDB (°C)</td>
                    <td colspan="2">Dehumidification DP / MCDB (°C)</td>
                </tr>
                <tr class="nasa-light">
                    <td>0.4%</td><td>1%</td>
                    <td>0.4%</td><td>1%</td>
                    <td>0.4%</td><td>1%</td>
                </tr>
                <tr>
                    <td style="font-weight:bold;">{hottest_month}</td>
                    <td>{db_max_ann:.1f} / {mcwb(df, db_max_ann):.1f}</td>
                    <td>{df['DB'].quantile(0.990):.1f} / {mcwb(df, df['DB'].quantile(0.990)):.1f}</td>
                    <td>{df['WB'].quantile(0.996):.1f} / {df.loc[(df['WB'] >= df['WB'].quantile(0.996) - 0.2) & (df['WB'] <= df['WB'].quantile(0.996) + 0.2), 'DB'].mean():.1f}</td>
                    <td>{df['WB'].quantile(0.990):.1f} / {df.loc[(df['WB'] >= df['WB'].quantile(0.990) - 0.2) & (df['WB'] <= df['WB'].quantile(0.990) + 0.2), 'DB'].mean():.1f}</td>
                    <td>N/A</td><td>N/A</td>
                </tr>
            </table>

            <table>
                <tr><th colspan="17" class="nasa-blue">Monthly Climatic Design Conditions</th></tr>
                <tr class="nasa-light">
                    <td rowspan="3" style="width: 60px; font-size:10px;">Month</td>
                    <td colspan="7">Temperatures, Degree-Days and Wind</td>
                    <td colspan="4" style="background-color: #d1e2f3;">Monthly Design Dry Bulb and<br>Mean Coincident Wet Bulb (°C)</td>
                    <td colspan="4" style="background-color: #ffe6cc;">Monthly Design Wet Bulb and<br>Mean Coincident Dry Bulb (°C)</td>
                    <td rowspan="3" style="background-color: #ccffcc;">Mean Daily<br>Temp Range<br>(°C)</td>
                </tr>
                <tr class="nasa-light">
                    <td rowspan="2">DB Avg<br>(°C)</td>
                    <td rowspan="2">DB Std<br>(°C)</td>
                    <td rowspan="2">WS Avg<br>(m/s)</td>
                    <td colspan="2">HDD (°C)</td>
                    <td colspan="2">CDD (°C)</td>
                    <td colspan="2" style="background-color: #d1e2f3;">0.4%</td>
                    <td colspan="2" style="background-color: #d1e2f3;">2%</td>
                    <td colspan="2" style="background-color: #ffe6cc;">0.4%</td>
                    <td colspan="2" style="background-color: #ffe6cc;">2%</td>
                </tr>
                <tr class="nasa-light">
                    <td>Base 10</td><td>Base 18.3</td>
                    <td>Base 10</td><td>Base 18.3</td>
                    <td style="background-color: #d1e2f3;">DB</td><td style="background-color: #d1e2f3;">MCWB</td>
                    <td style="background-color: #d1e2f3;">DB</td><td style="background-color: #d1e2f3;">MCWB</td>
                    <td style="background-color: #ffe6cc;">WB</td><td style="background-color: #ffe6cc;">MCDB</td>
                    <td style="background-color: #ffe6cc;">WB</td><td style="background-color: #ffe6cc;">MCDB</td>
                </tr>
                {filas_monthly}
            </table>
            
            <div class="footer">Nota: {fuente} Algunos parámetros avanzados (DP, Entalpía, Radiación) han sido omitidos si la matriz original EPW o NASA no los incluye.</div>
        </body></html>"""
        
        pdf_file = HTML(string=html_content).write_pdf()
        st.success("¡Matriz Completa Estilo NASA POWER generada con éxito!")
        st.download_button("📥 Descargar PDF Premium (NASA Format)", data=pdf_file, file_name=f"NASA_POWER_Format_{city_display.replace(' - ', '_')}.pdf", mime="application/pdf")
