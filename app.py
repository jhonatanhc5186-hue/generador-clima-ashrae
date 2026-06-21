import streamlit as st
import pandas as pd
import requests
from weasyprint import HTML

st.set_page_config(page_title="Generador ASHRAE", layout="wide")
st.title("🌍 Generador de Reportes Climáticos ASHRAE")

col1, col2, col3 = st.columns(3)
lat = col1.number_input("Latitud", value=-9.5822, format="%.4f")
lon = col2.number_input("Longitud", value=-77.0234, format="%.4f")
year = col3.selectbox("Año de análisis:", list(range(2024, 2014, -1)))

if st.button("Generar Reporte"):
    with st.spinner("Generando reporte con formato idéntico..."):
        # 1. Cálculo de datos
        url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET&community=SB&longitude={lon}&latitude={lat}&start={year}0101&end={year}1231&format=JSON"
        res = requests.get(url).json()
        df = pd.DataFrame({'DB': list(res['properties']['parameter']['T2M'].values()), 
                           'WB': list(res['properties']['parameter']['T2MWET'].values())})
        df['Month'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').month
        df['Day'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').date

        def calc_mcwb(sub, t):
            h = sub[(sub['DB'] >= t - 0.5) & (sub['DB'] <= t + 0.5)]
            return h['WB'].mean() if not h.empty else sub['WB'].max()

        data_rows = []
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        
        for m in range(1, 13):
            df_m = df[df['Month'] == m]
            if df_m.empty: continue
            
            # Cálculos
            db04 = df_m['DB'].quantile(0.996)
            db20 = df_m['DB'].quantile(0.980)
            db996 = df_m['DB'].quantile(0.004)
            db990 = df_m['DB'].quantile(0.010)
            range_c = (df_m.groupby('Day')['DB'].max() - df_m.groupby('Day')['DB'].min()).mean()
            
            data_rows.append({
                'Mes': meses[m-1],
                'DB04': db04, 'DB04F': (db04*9/5)+32, 
                'MCWB04': calc_mcwb(df_m, db04), 'MCWB04F': (calc_mcwb(df_m, db04)*9/5)+32,
                'DB20': db20, 'DB20F': (db20*9/5)+32, 
                'MCWB20': calc_mcwb(df_m, db20), 'MCWB20F': (calc_mcwb(df_m, db20)*9/5)+32,
                'H996': db996, 'H996F': (db996*9/5)+32, 
                'H990': db990, 'H990F': (db990*9/5)+32, 
                'Range': range_c, 'RangeF': range_c*9/5
            })

        # 2. HTML Preciso (CSS aplicado para coincidir con tu PDF)
        filas = "".join([f"""<tr>
            <td style="text-align:left; font-weight:bold;">{r['Mes']}</td>
            <td>{r['DB04']:.1f}</td><td>{r['DB04F']:.1f}</td>
            <td>{r['MCWB04']:.1f}</td><td>{r['MCWB04F']:.1f}</td>
            <td>{r['DB20']:.1f}</td><td>{r['DB20F']:.1f}</td>
            <td>{r['MCWB20']:.1f}</td><td>{r['MCWB20F']:.1f}</td>
            <td>{r['H996']:.1f}</td><td>{r['H996F']:.1f}</td>
            <td>{r['H990']:.1f}</td><td>{r['H990F']:.1f}</td>
            <td>{r['Range']:.1f}</td><td>{r['RangeF']:.1f}</td>
        </tr>""" for r in data_rows])

        html_content = f"""
        <html><head><style>
            body {{ font-family: sans-serif; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 9px; }}
            th, td {{ border: 1px solid #999; padding: 4px; text-align: center; }}
            .c1 {{ background-color: #2e75b6; color: white; }}
            .c2 {{ background-color: #c65911; color: white; }}
            .c3 {{ background-color: #548235; color: white; }}
        </style></head>
        <body>
            <h2 style="color: #2e75b6; border-bottom: 3px solid #2e75b6;">CONDICIONES CLIMÁTICAS MENSUALES DE DISEÑO</h2>
            <p><strong>Ubicación:</strong> NASA Data | <strong>Latitud:</strong> {lat} | <strong>Longitud:</strong> {lon}</p>
            <table>
                <tr><th rowspan="2" class="c1">Mes</th><th colspan="8" class="c1">Refrigeración (Cooling)</th><th colspan="4" class="c2">Calefacción (Heating)</th><th colspan="2" class="c3">MCDBR</th></tr>
                <tr><th colspan="2" class="c1">DB 0.4%</th><th colspan="2" class="c1">MCWB 0.4%</th><th colspan="2" class="c1">DB 2.0%</th><th colspan="2" class="c1">MCWB 2.0%</th><th colspan="2" class="c2">DB 99.6%</th><th colspan="2" class="c2">DB 99.0%</th><th colspan="2" class="c3">Δ°C | Δ°F</th></tr>
                {filas}
            </table>
        </body></html>"""
        
        pdf_file = HTML(string=html_content).write_pdf()
        st.success("¡Reporte generado con el formato exacto!")
        st.download_button("📥 Descargar Reporte", data=pdf_file, file_name="reporte_ashrae_pro.pdf", mime="application/pdf")
