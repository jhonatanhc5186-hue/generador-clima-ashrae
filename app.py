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
    with st.spinner("Procesando cálculos..."):
        # 1. Obtención de datos
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
            data_rows.append({
                'Mes': meses[m-1],
                'DB04': db_04, 'DB04F': (db_04 * 9/5) + 32,
                'MCWB04': calc_mcwb(df_m, db_04), 'MCWB04F': (calc_mcwb(df_m, db_04) * 9/5) + 32,
                'DB20': db_20, 'DB20F': (db_20 * 9/5) + 32,
                'MCWB20': calc_mcwb(df_m, db_20), 'MCWB20F': (calc_mcwb(df_m, db_20) * 9/5) + 32
            })

        # 3. Construcción del HTML (Corregida)
        filas = ""
        for r in data_rows:
            filas += f"<tr><td>{r['Mes']}</td><td>{r['DB04']:.1f}</td><td>{r['DB04F']:.1f}</td><td>{r['MCWB04']:.1f}</td><td>{r['MCWB04F']:.1f}</td><td>{r['DB20']:.1f}</td><td>{r['DB20F']:.1f}</td><td>{r['MCWB20']:.1f}</td><td>{r['MCWB20F']:.1f}</td></tr>"

        html_content = f"""
<html>
<body>
    <h1>Reporte ASHRAE</h1>
    <table border="1">
        <tr><th>Mes</th><th>DB 0.4% °C</th><th>°F</th><th>MCWB 0.4% °C</th><th>°F</th><th>DB 2.0% °C</th><th>°F</th><th>MCWB 2.0% °C</th><th>°F</th></tr>
        {filas}
    </table>
</body>
</html>
"""
        
        # 4. Generar PDF
        pdf_file = HTML(string=html_content).write_pdf()
        st.success("¡Reporte listo!")
        st.download_button("📥 Descargar PDF", data=pdf_file, file_name="reporte.pdf", mime="application/pdf")
