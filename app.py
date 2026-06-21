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
    with st.spinner("Procesando datos complejos..."):
        # 1. Obtención de datos NASA
        url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET&community=SB&longitude={lon}&latitude={lat}&start={year}0101&end={year}1231&format=JSON"
        res = requests.get(url).json()
        df = pd.DataFrame({'DB': list(res['properties']['parameter']['T2M'].values()), 
                           'WB': list(res['properties']['parameter']['T2MWET'].values())})
        df['Month'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').month
        df['Day'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').date

        # 2. Cálculos ASHRAE
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
            range_c = (df_m.groupby('Day')['DB'].max() - df_m.groupby('Day')['DB'].min()).mean()
            
            data_rows.append({
                'Mes': meses[m-1],
                'DB_04': db_04, 'DB_04_F': (db_04 * 9/5) + 32,
                'MCWB_04': calc_mcwb(df_m, db_04), 'MCWB_04_F': (calc_mcwb(df_m, db_04) * 9/5) + 32,
                'DB_20': db_20, 'DB_20_F': (db_20 * 9/5) + 32,
                'MCWB_20': calc_mcwb(df_m, db_20), 'MCWB_20_F': (calc_mcwb(df_m, db_20) * 9/5) + 32,
                'H_996': db_996, 'H_996_F': (db_996 * 9/5) + 32,
                'H_990': db_990, 'H_990_F': (db_990 * 9/5) + 32,
                'Range': range_c, 'Range_F': range_c * 9/5
            })

        # 3. HTML con todas las columnas
        filas = "".join([f"""<tr>
            <td>{r['Mes']}</td>
            <td>{r['DB_04']:.1f}</td><td>{r['DB_04_F']:.1f}</td>
            <td>{r['MCWB_04']:.1f}</td><td>{r['MCWB_04_F']:.1f}</td>
            <td>{r['DB_20']:.1f}</td><td>{r['DB_20_F']:.1f}</td>
            <td>{r['MCWB_20']:.1f}</td><td>{r['MCWB_20_F']:.1f}</td>
            <td>{r['H_996']:.1f}</td><td>{r['H_996_F']:.1f}</td>
            <td>{r['H_990']:.1f}</td><td>{r['H_990_F']:.1f}</td>
            <td>{r['Range']:.1f}</td><td>{r['Range_F']:.1f}</td>
        </tr>""" for r in data_rows])

        html_content = f"""
        <html><style>table {{width:100%; border-collapse:collapse;}} th,td {{border:1px solid black; padding:5px; text-align:center;}}</style>
        <body><h1>Reporte ASHRAE</h1>
        <table>
            <tr><th>Mes</th><th colspan="2">DB 0.4%</th><th colspan="2">MCWB 0.4%</th><th colspan="2">DB 2.0%</th><th colspan="2">MCWB 2.0%</th><th colspan="2">H 99.6%</th><th colspan="2">H 99.0%</th><th colspan="2">Range</th></tr>
            {filas}
        </table></body></html>"""
        
        pdf_file = HTML(string=html_content).write_pdf()
        st.success("¡Reporte completo generado!")
        st.download_button("📥 Descargar Reporte Completo", data=pdf_file, file_name="reporte_ashrae.pdf", mime="application/pdf")
