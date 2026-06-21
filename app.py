import streamlit as st
import pandas as pd
import requests
from weasyprint import HTML

st.set_page_config(page_title="Generador ASHRAE", layout="wide")
st.title("🌍 Generador de Reportes Climáticos ASHRAE")

col1, col2, col3 = st.columns(3)
lat = col1.number_input("Latitud", value=-9.5822, format="%.4f")
lon = col2.number_input("Longitud", value=-77.0234, format="%.4f")
year = col3.selectbox("Año:", list(range(2024, 2014, -1)))

if st.button("Generar Reporte"):
    with st.spinner("Generando reporte con formato idéntico..."):
        # 1. Obtención de datos NASA
        url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET&community=SB&longitude={lon}&latitude={lat}&start={year}0101&end={year}1231&format=JSON"
        res = requests.get(url).json()
        
        # Extracción de datos
        alt = round(res['geometry']['coordinates'][2], 1)
        df = pd.DataFrame({'DB': list(res['properties']['parameter']['T2M'].values()), 
                           'WB': list(res['properties']['parameter']['T2MWET'].values())})
        df['Month'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').month
        df['Day'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').date

        # 2. Cálculos Estadísticos
        def calc_mcwb(sub, t):
            h = sub[(sub['DB'] >= t - 0.5) & (sub['DB'] <= t + 0.5)]
            return h['WB'].mean() if not h.empty else sub['WB'].max()

        data_rows = []
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        
        for m in range(1, 13):
            df_m = df[df['Month'] == m]
            if df_m.empty: continue
            
            db_04 = df_m['DB'].quantile(0.996)
            db_20 = df_m['DB'].quantile(0.980)
            db_996 = df_m['DB'].quantile(0.004)
            db_990 = df_m['DB'].quantile(0.010)
            
            daily_max = df_m.groupby('Day')['DB'].max()
            daily_min = df_m.groupby('Day')['DB'].min()
            range_c = (daily_max - daily_min).mean()
            
            data_rows.append({
                'Mes': meses[m-1],
                'DB04': db_04, 'DB04F': (db_04*9/5)+32, 
                'MCWB04': calc_mcwb(df_m, db_04), 'MCWB04F': (calc_mcwb(df_m, db_04)*9/5)+32,
                'DB20': db_20, 'DB20F': (db_20*9/5)+32, 
                'MCWB20': calc_mcwb(df_m, db_20), 'MCWB20F': (calc_mcwb(df_m, db_20)*9/5)+32,
                'H996': db_996, 'H996F': (db_996*9/5)+32, 
                'H990': db_990, 'H990F': (db_990*9/5)+32, 
                'RangeC': range_c, 'RangeF': range_c*9/5
            })

        # 3. Construcción del HTML preciso (Igual a tu imagen)
        filas = "".join([f"""<tr>
            <td style="text-align:left; font-weight:bold;">{r['Mes']}</td>
            <td>{r['DB04']:.1f}</td><td>{r['DB04F']:.1f}</td>
            <td>{r['MCWB04']:.1f}</td><td>{r['MCWB04F']:.1f}</td>
            <td>{r['DB20']:.1f}</td><td>{r['DB20F']:.1f}</td>
            <td>{r['MCWB20']:.1f}</td><td>{r['MCWB20F']:.1f}</td>
            <td>{r['H996']:.1f}</td><td>{r['H996F']:.1f}</td>
            <td>{r['H990']:.1f}</td><td>{r['H990F']:.1f}</td>
            <td>{r['RangeC']:.1f}</td><td>{r['RangeF']:.1f}</td>
        </tr>""" for r in data_rows])

        html_content = f"""
        <html><head><style>
            body {{ font-family: sans-serif; font-size: 10px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ border: 1px solid #999; padding: 4px; text-align: center; }}
            .c1 {{ background-color: #2e75b6; color: white; }}
            .c2 {{ background-color: #c65911; color: white; }}
            .c3 {{ background-color: #548235; color: white; }}
        </style></head>
        <body>
            <h2 style="color: #2e75b6; border-bottom: 3px solid #2e75b6;">CONDICIONES CLIMÁTICAS MENSUALES DE DISEÑO</h2>
            <p><strong>Ubicación:</strong> San Marcos, Perú | <strong>Latitud:</strong> {lat} | <strong>Longitud:</strong> {lon} | <strong>Elevación:</strong> {alt} m</p>
            <table>
                <tr>
                    <th rowspan="2" class="c1">Mes</th>
                    <th colspan="8" class="c1">Refrigeración (Cooling)</th>
                    <th colspan="4" class="c2">Calefacción (Heating)</th>
                    <th colspan="2" class="c3">MCDBR</th>
                </tr>
                <tr>
                    <th colspan="2" class="c1">DB 0.4%</th><th colspan="2" class="c1">MCWB 0.4%</th>
                    <th colspan="2" class="c1">DB 2.0%</th><th colspan="2" class="c1">MCWB 2.0%</th>
                    <th colspan="2" class="c2">DB 99.6%</th><th colspan="2" class="c2">DB 99.0%</th>
                    <th colspan="2" class="c3">Δ°C | Δ°F</th>
                </tr>
                <tr>
                    <td></td><th>°C</th><th>°F</th><th>°C</th><th>°F</th><th>°C</th><th>°F</th><th>°C</th><th>°F</th><th>°C</th><th>°F</th><th>°C</th><th>°F</th><th>°C</th><th>°F</th>
                </tr>
                {filas}
            </table>
            <p style="font-size: 8px; color: #666;">Generado mediante reanálisis de datos NASA POWER (Año {year}). Procesado metodológicamente para aproximación de condiciones ASHRAE. Altitud nativa de la NASA.</p>
        </body></html>"""
        
        pdf_file = HTML(string=html_content).write_pdf()
        st.success("¡Reporte generado con el formato exacto!")
        st.download_button("📥 Descargar Reporte Identico", data=pdf_file, file_name="Reporte_ASHRAE_Identico.pdf", mime="application/pdf")
