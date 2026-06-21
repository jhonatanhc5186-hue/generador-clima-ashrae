import streamlit as st
import pandas as pd
import requests
import os
from weasyprint import HTML

st.set_page_config(page_title="Generador ASHRAE Pro", layout="wide")
st.title("🌍 Generador de Reportes Climáticos ASHRAE")

# 1. Función para decodificar archivos locales con corrección geográfica
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
                if p in ['AP', 'Intl', 'TMYx'] or p.isdigit() or ('-' in p and p.split('-')[0].isdigit()):
                    break
                city_words.append(p)
            
            base_name = " ".join(city_words)
            ciudad = base_name.split('-')[0].strip() 
            
            # --- CORRECCIÓN DE ERRORES DE ORIGEN (CLIMATE.ONEBUILDING) ---
            correcciones = {
                "Tacna": "Tacna",
                "Ilo": "Moquegua"
            }
            if ciudad in correcciones:
                departamento = correcciones[ciudad]
            # -------------------------------------------------------------

            return f"{pais} - {departamento} - {ciudad}"
            
        return filename.replace(".epw", "")
    except:
        return filename

# 2. Función para obtener ubicación real por coordenadas
def get_location_name(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        headers = {'User-Agent': 'GeneradorASHRAE_Peru_v3'}
        response = requests.get(url, headers=headers, timeout=5).json()
        address = response.get('address', {})
        
        pais = address.get('country', 'Perú')
        departamento = address.get('state', address.get('region', ''))
        ciudad = address.get('city', address.get('town', address.get('village', address.get('suburb', 'Ubicación Desconocida'))))
        
        if departamento:
            return f"{pais} - {departamento} - {ciudad}"
        return f"{pais} - {ciudad}"
    except:
        return f"Coordenadas [Lat: {lat}, Lon: {lon}]"

# 3. Función para calcular Presión Atmosférica Estándar (kPa)
def calc_stdp(elev_m):
    try:
        z = float(elev_m)
        p = 101.325 * (1 - 2.25577e-5 * z)**5.25588
        return f"{p:.2f}"
    except:
        return "101.32"

# 4. Función para formatear coordenadas (N/S, E/W)
def format_coord(val, is_lat):
    try:
        v = float(val)
        if is_lat:
            return f"{abs(v):.3f}{'N' if v >= 0 else 'S'}"
        else:
            return f"{abs(v):.3f}{'E' if v >= 0 else 'W'}"
    except:
        return str(val)

# 5. Función para mapear archivos locales
def get_epw_mapping():
    if not os.path.exists("data"): return {}
    files = [f for f in os.listdir("data") if f.endswith(".epw")]
    return {clean_city_name(f): f for f in sorted(files)}

# --- INTERFAZ STREAMLIT ---
col1, col2, col3 = st.columns(3)
file_map = get_epw_mapping()

OPCION_MANUAL = "-- Ingresar Coordenadas Manualmente --"
selected_city = col1.selectbox("Seleccionar ciudad:", [OPCION_MANUAL] + list(file_map.keys()))

usar_local = selected_city != OPCION_MANUAL

lat = col2.number_input("Latitud", value=-12.022, format="%.4f", disabled=usar_local)
lon = col3.number_input("Longitud", value=-77.114, format="%.4f", disabled=usar_local)

periodo_opciones = [
    "2023 (1 Año de prueba)", 
    "2019-2023 (5 Años)", 
    "2014-2023 (10 Años)", 
    "2009-2023 (15 Años - Estándar ASHRAE)"
]
periodo_str = col3.selectbox("Periodo Satelital NASA:", periodo_opciones, disabled=usar_local)

if st.button("Generar Reporte Profesional"):
    with st.spinner("Procesando matriz meteorológica. (Aviso: un periodo de 15 años puede tardar ~25 segundos en descargar)..."):
        fuente = ""
        df = None
        city_display = "Ubicación"
        alt_display = "0"
        period_display = "N/A"
        wmo_display = "N/A"
        start_date_for_range = "2024"

        # A) LÓGICA LOCAL (EPW PRE-CARGADO)
        if usar_local:
            filename = file_map[selected_city]
            city_display = selected_city.upper()
            
            period_display = "TMYx (Año Típico)"
            try:
                partes_punto = filename.replace(".epw", "").split('.')
                for p in partes_punto:
                    if "-" in p and len(p) == 9 and p.split('-')[0].isdigit():
                        period_display = f"{p} (TMYx)"
                        break
            except:
                pass

            try:
                with open(f"data/{filename}", 'r', encoding='utf-8') as f:
                    first_line = f.readline()
                    header_data = first_line.split(',')
                    wmo_display = header_data[5].strip()
                    lat = float(header_data[6])
                    lon = float(header_data[7])
                    alt_display = header_data[9].strip()
            except:
                pass 

            df = pd.read_csv(f"data/{filename}", skiprows=8, header=None, usecols=[1,2,6,8], names=['Month', 'Day', 'DB', 'WB'])
            fuente = "Fuente de datos: EnergyPlus (Archivo climático EPW)."
            start_date_for_range = "2024-01-01"

        # B) LÓGICA MANUAL (SATELITAL NASA - MULTIAÑO)
        else:
            city_display = get_location_name(lat, lon).upper()
            wmo_display = "SATELITAL"
            
            if "15 Años" in periodo_str: start_year, end_year = 2009, 2023
            elif "10 Años" in periodo_str: start_year, end_year = 2014, 2023
            elif "5 Años" in periodo_str: start_year, end_year = 2019, 2023
            else: start_year, end_year = 2023, 2023
                
            period_display = f"{start_year}-{end_year}"
            start_date_for_range = f"{start_year}-01-01"
            
            dfs = []
            for y in range(start_year, end_year + 1):
                url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET&community=SB&longitude={lon}&latitude={lat}&start={y}0101&end={y}1231&format=JSON"
                res = requests.get(url).json()
                
                if y == start_year:
                    alt_display = str(round(res['geometry']['coordinates'][2], 1))
                
                db_vals = list(res['properties']['parameter']['T2M'].values())
                wb_vals = list(res['properties']['parameter']['T2MWET'].values())
                
                temp_df = pd.DataFrame({'DB': db_vals, 'WB': wb_vals})
                temp_df['Month'] = pd.date_range(start=f"{y}-01-01", periods=len(temp_df), freq='h').month
                dfs.append(temp_df)
                
            df = pd.concat(dfs, ignore_index=True)
            horas_totales = (end_year - start_year + 1) * 8760
            fuente = f"Generado mediante reanálisis de datos satelitales NASA ({start_year}-{end_year}). Extracción percentilar matemática derivada de {horas_totales} horas de data continua."

        # Cálculos de Ingeniería ASHRAE
        df['Day'] = pd.date_range(start=start_date_for_range, periods=len(df), freq='h').date
        
        def calc_mcwb(sub, t):
            h = sub[(sub['DB'] >= t - 0.5) & (sub['DB'] <= t + 0.5)]
            return h['WB'].mean() if not h.empty else sub['WB'].max()

        data_rows = []
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        for m in range(1, 13):
            df_m = df[df['Month'] == m]
            if df_m.empty: continue
            
            db04 = df_m['DB'].quantile(0.996)
            db20 = df_m['DB'].quantile(0.980)
            db996 = df_m['DB'].quantile(0.004)
            db990 = df_m['DB'].quantile(0.010)
            range_c = (df_m.groupby('Day')['DB'].max() - df_m.groupby('Day')['DB'].min()).mean()
            
            data_rows.append({
                'Mes': meses[m-1],
                'DB04': db04, 'DB04F': (db04*9/5)+32, 'MCWB04': calc_mcwb(df_m, db04), 'MCWB04F': (calc_mcwb(df_m, db04)*9/5)+32,
                'DB20': db20, 'DB20F': (db20*9/5)+32, 'MCWB20': calc_mcwb(df_m, db20), 'MCWB20F': (calc_mcwb(df_m, db20)*9/5)+32,
                'DB996': db996, 'DB996F': (db996*9/5)+32, 'DB990': db990, 'DB990F': (db990*9/5)+32,
                'RangeC': range_c, 'RangeF': range_c*9/5
            })

        lat_str = format_coord(lat, True)
        lon_str = format_coord(lon, False)
        stdp_display = calc_stdp(alt_display)
        
        # Calcular altitud en pies
        try:
            alt_ft = float(alt_display) * 3.28084
            alt_ft_str = f"{alt_ft:.1f}"
        except:
            alt_ft_str = "0.0"

        # --- CONSTRUCCIÓN DE HTML PREMIUM ---
        filas = "".join([f"""
        <tr>
            <td style="text-align:left; font-weight:bold; background-color:#f8f9fa;">{r['Mes']}</td>
            <td>{r['DB04']:.1f}</td><td>{r['DB04F']:.1f}</td><td>{r['MCWB04']:.1f}</td><td>{r['MCWB04F']:.1f}</td>
            <td>{r['DB20']:.1f}</td><td>{r['DB20F']:.1f}</td><td>{r['MCWB20']:.1f}</td><td>{r['MCWB20F']:.1f}</td>
            <td>{r['DB996']:.1f}</td><td>{r['DB996F']:.1f}</td><td>{r['DB990']:.1f}</td><td>{r['DB990F']:.1f}</td>
            <td>{r['RangeC']:.1f}</td><td>{r['RangeF']:.1f}</td>
        </tr>""" for r in data_rows])
        
        html_content = f"""
        <html><head><style>
            @page {{ size: A4 landscape; margin: 1cm; }}
            body {{ font-family: 'Times New Roman', serif; font-size: 11px; color: #000; }}
            
            .location-header {{ font-size: 16px; font-weight: bold; text-align: center; margin-top: 15px; margin-bottom: 15px; }}
            
            table {{ width: 100%; border-collapse: collapse; }}
            .meta-table {{ font-size: 12px; margin-bottom: 5px; border-bottom: 3px solid #1e5a99; padding-bottom: 5px; }}
            .meta-table td {{ border: none; text-align: center; padding: 3px; }}
            
            .data-table {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; margin-top: 15px; box-shadow: 0px 2px 5px rgba(0,0,0,0.1); font-size: 10px; }}
            .data-table th, .data-table td {{ border: 1px solid #c2c2c2; padding: 6px; text-align: center; }}
            .data-table th {{ font-weight: bold; font-size: 9px; }}
            .azul {{ background-color: #2e75b6; color: white; border: 1px solid #1e5a99; }}
            .naranja {{ background-color: #e46c0a; color: white; border: 1px solid #b35508; }}
            .verde {{ background-color: #28a745; color: white; border: 1px solid #1e7e34; }}
            .data-table tr:nth-child(even) td {{ background-color: #fdfdfd; }}
            
            .footer {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 9px; color: #555; margin-top: 15px; font-style: italic; }}
        </style></head>
        <body>
            <div class="location-header">{city_display} (WMO: {wmo_display})</div>
            
            <table class="meta-table">
                <tr>
                    <td>Lat: <strong>{lat_str}</strong></td>
                    <td>Lon: <strong>{lon_str}</strong></td>
                    <td>Elev: <strong>{alt_display} m ({alt_ft_str} ft)</strong></td>
                    <td>StdP: <strong>{stdp_display}</strong></td>
                    <td>Time zone: <strong>-5.00 (W05)</strong></td>
                    <td>Period: <strong>{period_display}</strong></td>
                    <td>WBAN: <strong>99999</strong></td>
                </tr>
            </table>
            
            <table class="data-table">
                <tr>
                    <th rowspan="3" class="azul" style="vertical-align: middle;">Mes</th>
                    <th colspan="8" class="azul">Refrigeración (Cooling)</th>
                    <th colspan="4" class="naranja">Calefacción (Heating)</th>
                    <th colspan="2" class="verde">MCDBR</th>
                </tr>
                <tr>
                    <th colspan="2" class="azul">DB 0.4%</th><th colspan="2" class="azul">MCWB 0.4%</th>
                    <th colspan="2" class="azul">DB 2.0%</th><th colspan="2" class="azul">MCWB 2.0%</th>
                    <th colspan="2" class="naranja">DB 99.6%</th><th colspan="2" class="naranja">DB 99.0%</th>
                    <th colspan="2" class="verde">Δ°C | Δ°F</th>
                </tr>
                <tr>
                    <th class="azul">°C</th><th class="azul">°F</th><th class="azul">°C</th><th class="azul">°F</th>
                    <th class="azul">°C</th><th class="azul">°F</th><th class="azul">°C</th><th class="azul">°F</th>
                    <th class="naranja">°C</th><th class="naranja">°F</th><th class="naranja">°C</th><th class="naranja">°F</th>
                    <th class="verde">°C</th><th class="verde">°F</th>
                </tr>
                {filas}
            </table>
            
            <div class="footer">{fuente}</div>
        </body></html>"""
        
        pdf_file = HTML(string=html_content).write_pdf()
        st.success("¡Reporte maestro generado!")
        st.download_button("📥 Descargar PDF Premium", data=pdf_file, file_name=f"Reporte_ASHRAE_{city_display.replace(' - ', '_')}.pdf", mime="application/pdf")
