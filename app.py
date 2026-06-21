import streamlit as st
import pandas as pd
import requests
import os
from weasyprint import HTML

st.set_page_config(page_title="Generador ASHRAE Pro", layout="wide")
st.title("🌍 Generador de Reportes Climáticos ASHRAE")

# 1. Función para listar archivos en la carpeta 'data'
def get_epw_files():
    if not os.path.exists("data"): return []
    return [f for f in os.listdir("data") if f.endswith(".epw")]

# --- Interfaz de usuario ---
col1, col2, col3 = st.columns(3)

# Aquí listamos los archivos automáticamente
epw_options = get_epw_files()
selected_file = col1.selectbox("Selecciona una estación local:", ["-- Usar datos NASA (Online) --"] + epw_options)

lat = col2.number_input("Latitud", value=-9.5822, format="%.4f")
lon = col3.number_input("Longitud", value=-77.0234, format="%.4f")
year = col3.selectbox("Año de análisis:", list(range(2024, 2014, -1)))

if st.button("Generar Reporte Profesional"):
    with st.spinner("Procesando datos..."):
        fuente = ""
        df = None
        city_name = "Ubicación"

        # A) LÓGICA LOCAL (Si elegiste un archivo de la lista)
        if selected_file != "-- Usar datos NASA (Online) --":
            try:
                # Nota: f"data/{selected_file}" busca dentro de la carpeta que creaste
                city_name = selected_file.replace(".epw", "").replace("_", " ")
                df = pd.read_csv(f"data/{selected_file}", skiprows=8, header=None, usecols=[1,2,6,8], names=['Month', 'Day', 'DB', 'WB'])
                fuente = f"Repositorio Local: {selected_file}"
                alt = "N/A"
            except Exception as e:
                st.error(f"Error al leer el archivo EPW: {e}")

        # B) FALLBACK NASA (Si elegiste la opción Online)
        if df is None:
            url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET&community=SB&longitude={lon}&latitude={lat}&start={year}0101&end={year}1231&format=JSON"
            res = requests.get(url).json()
            alt = round(res['geometry']['coordinates'][2], 1)
            city_name = f"Lat: {lat}, Lon: {lon}"
            df = pd.DataFrame({'DB': list(res['properties']['parameter']['T2M'].values()), 
                               'WB': list(res['properties']['parameter']['T2MWET'].values())})
            df['Month'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').month
            fuente = "NASA POWER (Datos Satelitales)"

        # Cálculos (Igual que siempre)
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
                'Mes': meses[m-1], 'DB04': db04, 'DB04F': (db04*9/5)+32, 'MCWB04': calc_mcwb(df_m, db04), 'MCWB04F': (calc_mcwb(df_m, db04)*9/5)+32,
                'DB20': db20, 'DB20F': (db20*9/5)+32, 'MCWB20': calc_mcwb(df_m, db20), 'MCWB20F': (calc_mcwb(df_m, db20)*9/5)+32
            })

        # HTML
        filas = "".join([f"<tr><td style='text-align:left; font-weight:bold;'>{r['Mes']}</td><td>{r['DB04']:.1f}</td><td>{r['DB04F']:.1f}</td><td>{r['MCWB04']:.1f}</td><td>{r['MCWB04F']:.1f}</td><td>{r['DB20']:.1f}</td><td>{r['DB20F']:.1f}</td><td>{r['MCWB20']:.1f}</td><td>{r['MCWB20F']:.1f}</td></tr>" for r in data_rows])
        
        html_content = f"""
        <html><style>
            @page {{ size: A4 landscape; margin: 1cm; }}
            body {{ font-family: sans-serif; font-size: 9px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ border: 1px solid #777; padding: 4px; text-align: center; }}
            .azul {{ background-color: #2e75b6; color: white; }}
        </style>
        <body>
            <h2 style="color: #2e75b6;">Reporte de {city_name}</h2>
            <table>
                <tr><th class="azul">Mes</th><th colspan="2" class="azul">DB 0.4%</th><th colspan="2" class="azul">MCWB 0.4%</th><th colspan="2" class="azul">DB 2.0%</th><th colspan="2" class="azul">MCWB 2.0%</th></tr>
                {filas}
            </table>
            <p><strong>Fuente de datos:</strong> {fuente}</p>
        </body></html>"""
        
        pdf_file = HTML(string=html_content).write_pdf()
        st.success("¡Reporte generado!")
        st.download_button("📥 Descargar PDF", data=pdf_file, file_name=f"Reporte_{city_name}.pdf", mime="application/pdf")
