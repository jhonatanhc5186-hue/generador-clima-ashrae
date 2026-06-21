import streamlit as st
import pandas as pd
import requests
import os
from weasyprint import HTML

st.set_page_config(page_title="Generador ASHRAE Pro", layout="wide")
st.title("🌍 Generador de Reportes Climáticos ASHRAE")

# Función para limpiar el nombre y mostrar solo la ciudad
def clean_city_name(filename):
    # Asumiendo el formato PER_REGION_Ciudad...
    parts = filename.split('_')
    if len(parts) >= 3:
        return parts[2].split('.')[0] # Extrae el nombre de la ciudad
    return filename

# Función para listar archivos y crear un diccionario de mapeo
def get_epw_mapping():
    if not os.path.exists("data"): return {}
    files = [f for f in os.listdir("data") if f.endswith(".epw")]
    # Crea un diccionario: {'Tarapoto': 'PER_SAM_Tarapoto...epw'}
    return {clean_city_name(f): f for f in files}

# --- Interfaz ---
col1, col2, col3 = st.columns(3)
file_map = get_epw_mapping()
selected_city = col1.selectbox("Selecciona la ciudad:", ["-- Usar datos NASA (Online) --"] + list(file_map.keys()))

lat = col2.number_input("Latitud", value=-9.5822, format="%.4f")
lon = col3.number_input("Longitud", value=-77.0234, format="%.4f")
year = col3.selectbox("Año de análisis:", list(range(2024, 2014, -1)))

if st.button("Generar Reporte Profesional"):
    with st.spinner("Generando reporte..."):
        fuente = ""
        df = None
        city_display = "Ubicación"

        # A) Lógica Local
        if selected_city != "-- Usar datos NASA (Online) --":
            filename = file_map[selected_city]
            city_display = selected_city
            df = pd.read_csv(f"data/{filename}", skiprows=8, header=None, usecols=[1,2,6,8], names=['Month', 'Day', 'DB', 'WB'])
            fuente = f"Repositorio Local: {filename}"
        
        # B) Lógica NASA
        if df is None:
            url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET&community=SB&longitude={lon}&latitude={lat}&start={year}0101&end={year}1231&format=JSON"
            res = requests.get(url).json()
            city_display = f"Lat: {lat}, Lon: {lon}"
            df = pd.DataFrame({'DB': list(res['properties']['parameter']['T2M'].values()), 
                               'WB': list(res['properties']['parameter']['T2MWET'].values())})
            df['Month'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').month
            fuente = "NASA POWER (Datos Satelitales)"

        # Cálculos
        df['Day'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').date
        
        def calc_mcwb(sub, t):
            h = sub[(sub['DB'] >= t - 0.5) & (sub['DB'] <= t + 0.5)]
            return h['WB'].mean() if not h.empty else sub['WB'].max()

        data_rows = []
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        for m in range(1, 13):
            df_m = df[df['Month'] == m]
            if df_m.empty: continue
            db04, db20 = df_m['DB'].quantile(0.996), df_m['DB'].quantile(0.980)
            data_rows.append({
                'Mes': meses[m-1], 'DB04': db04, 'DB04F': (db04*9/5)+32, 
                'MCWB04': calc_mcwb(df_m, db04), 'MCWB04F': (calc_mcwb(df_m, db04)*9/5)+32,
                'DB20': db20, 'DB20F': (db20*9/5)+32, 
                'MCWB20': calc_mcwb(df_m, db20), 'MCWB20F': (calc_mcwb(df_m, db20)*9/5)+32
            })

        # --- HTML Profesional ---
        filas = "".join([f"<tr><td style='text-align:left; font-weight:bold;'>{r['Mes']}</td><td>{r['DB04']:.1f}</td><td>{r['DB04F']:.1f}</td><td>{r['MCWB04']:.1f}</td><td>{r['MCWB04F']:.1f}</td><td>{r['DB20']:.1f}</td><td>{r['DB20F']:.1f}</td><td>{r['MCWB20']:.1f}</td><td>{r['MCWB20F']:.1f}</td></tr>" for r in data_rows])
        
        html_content = f"""
        <html><style>
            @page {{ size: A4 landscape; margin: 1cm; }}
            body {{ font-family: sans-serif; font-size: 10px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ border: 1px solid #777; padding: 5px; text-align: center; }}
            .azul {{ background-color: #2e75b6; color: white; }}
        </style>
        <body>
            <h2 style="color: #2e75b6;">Reporte de Condiciones Climáticas: {city_display}</h2>
            <table>
                <tr><th rowspan="2" class="azul">Mes</th><th colspan="2" class="azul">DB 0.4%</th><th colspan="2" class="azul">MCWB 0.4%</th><th colspan="2" class="azul">DB 2.0%</th><th colspan="2" class="azul">MCWB 2.0%</th></tr>
                <tr><th class="azul">°C</th><th class="azul">°F</th><th class="azul">°C</th><th class="azul">°F</th><th class="azul">°C</th><th class="azul">°F</th><th class="azul">°C</th><th class="azul">°F</th></tr>
                {filas}
            </table>
            <p style="font-size: 8px;"><strong>Fuente de datos:</strong> {fuente}</p>
        </body></html>"""
        
        pdf_file = HTML(string=html_content).write_pdf()
        st.success("¡Reporte listo!")
        st.download_button("📥 Descargar PDF", data=pdf_file, file_name=f"Reporte_{city_display}.pdf", mime="application/pdf")
