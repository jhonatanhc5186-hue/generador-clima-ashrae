import streamlit as st
import pandas as pd
import requests
from weasyprint import HTML

# Configuración de la App
st.set_page_config(page_title="Generador ASHRAE Profesional", layout="wide")
st.title("🌍 Generador de Reportes Climáticos ASHRAE")

# Inputs
col1, col2, col3 = st.columns(3)
lat = col1.number_input("Latitud", value=-9.5653, format="%.4f")
lon = col2.number_input("Longitud", value=-77.03638, format="%.4f")
year = col3.selectbox("Año de análisis:", list(range(2024, 2014, -1)))

# Función para obtener ubicación real (Geocodificación)
def get_location_name(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        headers = {'User-Agent': 'ReporteASHRAE_App'}
        response = requests.get(url, headers=headers, timeout=5).json()
        address = response.get('address', {})
        return address.get('city', address.get('town', address.get('village', 'Ubicación Desconocida')))
    except:
        return f"Lat: {lat}, Lon: {lon}"

if st.button("Generar Reporte Profesional"):
    with st.spinner("Procesando datos y aplicando formato profesional..."):
        # 1. Obtención de datos NASA
        url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET&community=SB&longitude={lon}&latitude={lat}&start={year}0101&end={year}1231&format=JSON"
        res = requests.get(url).json()
        alt = round(res['geometry']['coordinates'][2], 1)
        city_name = get_location_name(lat, lon)
        
        df = pd.DataFrame({'DB': list(res['properties']['parameter']['T2M'].values()), 
                           'WB': list(res['properties']['parameter']['T2MWET'].values())})
        df['Month'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').month
        df['Day'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').date

        # 2. Cálculos
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
                'H996': db996, 'H996F': (db996*9/5)+32, 'H990': db990, 'H990F': (db990*9/5)+32,
                'Range': range_c, 'RangeF': range_c*9/5
            })

        # 3. Construcción del HTML preciso
        filas = "".join([f"""<tr>
            <td style="text-align:left; font-weight:bold;">{r['Mes']}</td>
            <td>{r['DB04']:.1f}</td><td>{r['DB04F']:.1f}</td><td>{r['MCWB04']:.1f}</td><td>{r['MCWB04F']:.1f}</td>
            <td>{r['DB20']:.1f}</td><td>{r['DB20F']:.1f}</td><td>{r['MCWB20']:.1f}</td><td>{r['MCWB20F']:.1f}</td>
            <td>{r['H996']:.1f}</td><td>{r['H996F']:.1f}</td><td>{r['H990']:.1f}</td><td>{r['H990F']:.1f}</td>
            <td>{r['Range']:.1f}</td><td>{r['RangeF']:.1f}</td>
        </tr>""" for r in data_rows])

        html_content = f"""
        <html><head><style>
            @page {{ size: A4 landscape; margin: 0.5cm; }}
            body {{ font-family: 'Arial', sans-serif; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 8px; }}
            th, td {{ border: 1px solid #777; padding: 3px; text-align: center; }}
            .h_azul {{ background-color: #2e75b6; color: white; }}
            .h_naranja {{ background-color: #c65911; color: white; }}
            .h_verde {{ background-color: #548235; color: white; }}
        </style></head>
        <body>
            <h2 style="color: #2e75b6; border-bottom: 3px solid #2e75b6; margin: 2px 0;">CONDICIONES CLIMÁTICAS MENSUALES DE DISEÑO</h2>
            <p style="margin: 2px 0;"><strong>Ubicación:</strong> {city_name}, Perú | <strong>Latitud:</strong> {lat} | <strong>Longitud:</strong> {lon} | <strong>Elevación:</strong> {alt} m</p>
            <table>
                <tr><th rowspan="2" class="h_azul">Mes</th><th colspan="8" class="h_azul">Refrigeración (Cooling)</th><th colspan="4" class="h_naranja">Calefacción (Heating)</th><th colspan="2" class="h_verde">MCDBR</th></tr>
                <tr>
                    <th colspan="2" class="h_azul">DB 0.4%</th><th colspan="2" class="h_azul">MCWB 0.4%</th><th colspan="2" class="h_azul">DB 2.0%</th><th colspan="2" class="h_azul">MCWB 2.0%</th>
                    <th colspan="2" class="h_naranja">DB 99.6%</th><th colspan="2" class="h_naranja">DB 99.0%</th><th colspan="2" class="h_verde">Δ°C | Δ°F</th>
                </tr>
                <tr><td class="h_azul"></td><th>°C</th><th>°F</th><th>°C</th><th>°F</th><th>°C</th><th>°F</th><th>°C</th><th>°F</th><th>°C</th><th>°F</th><th>°C</th><th>°F</th><th>°C</th><th>°F</th></tr>
                {filas}
            </table>
            <p style="font-size: 7px; color: #444; margin-top: 5px;">Generado mediante reanálisis de datos NASA POWER (Año {year}). Procesado metodológicamente para aproximación de condiciones ASHRAE. Altitud nativa de la NASA.</p>
        </body></html>"""
        
        pdf_file = HTML(string=html_content).write_pdf()
        st.success("¡Reporte generado con formato oficial!")
        st.download_button("📥 Descargar PDF Formato Oficial", data=pdf_file, file_name=f"Reporte_Clima_{city_name}.pdf", mime="application/pdf")
