import streamlit as st
import pandas as pd
import requests
import os
from weasyprint import HTML

st.set_page_config(page_title="Generador ASHRAE Pro", layout="wide")
st.title("🌍 Generador de Reportes Climáticos ASHRAE")

# 1. Función para limpiar el nombre
def clean_city_name(filename):
    try:
        # Extrae "Chachapoyas" de "PER_AMA_Chachapoyas.AP.844440..."
        parts = filename.split('_')
        if len(parts) >= 3:
            return parts[2].split('.')[0].replace("-", " ")
        return filename.replace(".epw", "")
    except:
        return filename

# 2. Función para listar archivos locales
def get_epw_mapping():
    if not os.path.exists("data"): return {}
    files = [f for f in os.listdir("data") if f.endswith(".epw")]
    return {clean_city_name(f): f for f in files}

# --- INTERFAZ ---
col1, col2, col3 = st.columns(3)
file_map = get_epw_mapping()

# Etiqueta actualizada según tu solicitud
selected_city = col1.selectbox("Seleccionar ciudad:", ["-- Usar datos NASA (Online) --"] + list(file_map.keys()))

lat = col2.number_input("Latitud (Solo para NASA)", value=-9.5822, format="%.4f")
lon = col3.number_input("Longitud (Solo para NASA)", value=-77.0234, format="%.4f")
year = col3.selectbox("Año de análisis (Solo para NASA):", list(range(2024, 2014, -1)))

if st.button("Generar Reporte Profesional"):
    with st.spinner("Procesando datos y diseñando PDF Premium..."):
        fuente = ""
        df = None
        city_display = "Ubicación"
        alt_display = "N/A"

        # A) LÓGICA LOCAL (EPW)
        if selected_city != "-- Usar datos NASA (Online) --":
            filename = file_map[selected_city]
            city_display = selected_city
            
            # Lectura inteligente: Extraer Lat/Lon/Alt exactas del archivo EPW
            try:
                with open(f"data/{filename}", 'r', encoding='utf-8') as f:
                    first_line = f.readline()
                    header_data = first_line.split(',')
                    lat = float(header_data[6])
                    lon = float(header_data[7])
                    alt_display = header_data[9].strip()
            except:
                pass # Si falla, usa los valores por defecto

            df = pd.read_csv(f"data/{filename}", skiprows=8, header=None, usecols=[1,2,6,8], names=['Month', 'Day', 'DB', 'WB'])
            # Cita de fuente para archivos locales
            fuente = "Fuente de datos: EnergyPlus (Archivo climático EPW)."

        # B) LÓGICA NASA (Online)
        else:
            url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET&community=SB&longitude={lon}&latitude={lat}&start={year}0101&end={year}1231&format=JSON"
            res = requests.get(url).json()
            city_display = f"Coordenadas Satelitales"
            alt_display = str(round(res['geometry']['coordinates'][2], 1))
            df = pd.DataFrame({'DB': list(res['properties']['parameter']['T2M'].values()), 
                               'WB': list(res['properties']['parameter']['T2MWET'].values())})
            df['Month'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').month
            # Cita de fuente para NASA
            fuente = f"Generado mediante reanálisis de datos NASA POWER (Año {year}). Procesado metodológicamente para aproximación de condiciones ASHRAE. Altitud nativa de la NASA."

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
            p {{ margin: 4px 0; font-size: 11px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; box-shadow: 0px 2px 5px rgba(0,0,0,0.1); }}
            th, td {{ border: 1px solid #c2c2c2; padding: 6px; text-align: center; }}
            th {{ font-weight: bold; font-size: 9px; }}
            .azul {{ background-color: #2e75b6; color: white; border: 1px solid #1e5a99; }}
            .naranja {{ background-color: #e46c0a; color: white; border: 1px solid #b35508; }}
            .verde {{ background-color: #28a745; color: white; border: 1px solid #1e7e34; }}
            .footer {{ font-size: 9px; color: #555; margin-top: 15px; font-style: italic; }}
            tr:nth-child(even) td {{ background-color: #fdfdfd; }}
        </style></head>
        <body>
            <h2>CONDICIONES CLIMÁTICAS MENSUALES DE DISEÑO</h2>
            <p><strong>Ubicación:</strong> {city_display} | <strong>Latitud:</strong> {lat} | <strong>Longitud:</strong> {lon} | <strong>Elevación:</strong> {alt_display} m</p>
            
            <table>
                <tr>
                    <th rowspan="2" class="azul" style="vertical-align: middle;">Mes</th>
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
                    <td style="background-color: #f8f9fa; border-bottom: 2px solid #c2c2c2;"></td>
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
        st.success("¡Reporte generado con estándar profesional!")
        st.download_button("📥 Descargar PDF Premium", data=pdf_file, file_name=f"Reporte_{city_display}.pdf", mime="application/pdf")
