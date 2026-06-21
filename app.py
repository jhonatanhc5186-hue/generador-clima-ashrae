import streamlit as st
import pandas as pd
import requests
import os
from weasyprint import HTML

st.set_page_config(page_title="Generador ASHRAE Pro", layout="wide")
st.title("🌍 Generador de Reportes Climáticos ASHRAE")

# 1. Función para decodificar archivos locales (SOLO CIUDAD)
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
            
            # Paso 1: Unir las palabras separadas por puntos (Ej: La.Merced -> La Merced)
            subparts = parts[2].split('.')
            city_words = []
            for p in subparts:
                if p in ['AP', 'Intl'] or p.isdigit():
                    break
                city_words.append(p)
            
            base_name = " ".join(city_words)
            
            # Paso 2: AISLAR SOLO LA CIUDAD (Corta en el guion '-' y descarta la estación)
            ciudad = base_name.split('-')[0].strip()
            
            return f"{pais} - {departamento} - {ciudad}"
            
        return filename.replace(".epw", "")
    except:
        return filename

# 2. Función para geocodificación inversa
def get_location_name(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        headers = {'User-Agent': 'GeneradorASHRAE_Peru_v2'}
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

# 3. Función para listar archivos
def get_epw_mapping():
    if not os.path.exists("data"): return {}
    files = [f for f in os.listdir("data") if f.endswith(".epw")]
    return {clean_city_name(f): f for f in sorted(files)}

# --- INTERFAZ ---
col1, col2, col3 = st.columns(3)
file_map = get_epw_mapping()

OPCION_MANUAL = "-- Ingresar Coordenadas Manualmente --"
selected_city = col1.selectbox("Seleccionar ciudad:", [OPCION_MANUAL] + list(file_map.keys()))

usar_local = selected_city != OPCION_MANUAL

lat = col2.number_input("Latitud", value=-9.5822, format="%.4f", disabled=usar_local)
lon = col3.number_input("Longitud", value=-77.0234, format="%.4f", disabled=usar_local)
year = col3.selectbox("Año de análisis (Satelital):", list(range(2024, 2014, -1)), disabled=usar_local)

if st.button("Generar Reporte Profesional"):
    with st.spinner("Procesando datos y diseñando PDF Premium..."):
        fuente = ""
        df = None
        city_display = "Ubicación"
        alt_display = "N/A"

        # A) LÓGICA LOCAL (EPW)
        if usar_local:
            filename = file_map[selected_city]
            city_display = selected_city
            
            try:
                with open(f"data/{filename}", 'r', encoding='utf-8') as f:
                    first_line = f.readline()
                    header_data = first_line.split(',')
                    lat_real = float(header_data[6])
                    lon_real = float(header_data[7])
                    alt_display = header_data[9].strip()
                    lat = lat_real
                    lon = lon_real
            except:
                pass 

            df = pd.read_csv(f"data/{filename}", skiprows=8, header=None, usecols=[1,2,6,8], names=['Month', 'Day', 'DB', 'WB'])
            fuente = "Fuente de datos: EnergyPlus (Archivo climático EPW)."

        # B) LÓGICA COORDENADAS (NASA + GEOCODIFICACIÓN)
        else:
            city_display = get_location_name(lat, lon)
            
            url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET&community=SB&longitude={lon}&latitude={lat}&start={year}0101&end={year}1231&format=JSON"
            res = requests.get(url).json()
            alt_display = str(round(res['geometry']['coordinates'][2], 1))
            df = pd.DataFrame({'DB': list(res['properties']['parameter']['T2M'].values()), 
                               'WB': list(res['properties']['parameter']['T2MWET'].values())})
            df['Month'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').month
            fuente = f"Generado mediante reanálisis de datos satelitales (Año {year}). Procesado metodológicamente para aproximación de condiciones ASHRAE. Altitud nativa satelital."

        # Cálculos de Ingeniería
        df['Day'] = pd.date_range(start=f"2024-01-01", periods=len(df), freq='h').date
        
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
            body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 10px; color: #333; }}
            h2 {{ color: #1e5a99; border-bottom: 2px solid #1e5a99; padding-bottom: 5px; margin-bottom: 10px; font-size: 18px; }}
