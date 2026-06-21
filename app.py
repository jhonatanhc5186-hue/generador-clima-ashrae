import streamlit as st
import pandas as pd
import requests
from weasyprint import HTML

st.set_page_config(page_title="Generador ASHRAE", layout="wide")
st.title("🌍 Generador de Reportes Climáticos ASHRAE")

# Inputs
col1, col2, col3 = st.columns(3)
lat = col1.number_input("Latitud", value=-9.5822, format="%.4f")
lon = col2.number_input("Longitud", value=-77.0234, format="%.4f")
year = col3.selectbox("Año:", list(range(2024, 2014, -1)))

if st.button("Generar Reporte"):
    with st.spinner("Procesando datos ASHRAE..."):
        # 1. Obtención de datos
        url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET&community=SB&longitude={lon}&latitude={lat}&start={year}0101&end={year}1231&format=JSON"
        res = requests.get(url).json()
        df = pd.DataFrame({
            'DB': list(res['properties']['parameter']['T2M'].values()), 
            'WB': list(res['properties']['parameter']['T2MWET'].values())
        })
        df['Month'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').month
        
        # 2. Cálculo
        data_rows = []
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        for m in range(1, 13):
            df_m = df[df['Month'] == m]
            data_rows.append({
                'Mes': meses[m-1], 
                'DB_04': df_m['DB'].quantile(0.996), 
                'DB_20': df_m['DB'].quantile(0.980)
            })

        # 3. CONSTRUCCIÓN DE LA TABLA (Aquí estaba el error)
        filas_html = ""
        for r in data_rows:
            filas_html += f"<tr><td>{r['Mes']}</td><td>{r['DB_04']:.1f}</td><td>{r['DB_20']:.1f}</td></tr>"

        html_content = f"""
        <html>
        <body>
            <h1>Reporte Climático ASHRAE</h1>
            <table border="1" style="width:100%; text-align:center;">
                <tr><th>Mes</th><th>DB 0.4%</th><th>DB 2.0%</th></tr>
                {filas_html}
            </table>
        </body>
        </html>
        """
        
        # 4. Generar PDF
        pdf_file = HTML(string=html_content).write_pdf()
        
        st.success("¡Reporte listo!")
        st.download_button("📥 Descargar PDF", data=pdf_file, file_name="reporte_ashrae.pdf", mime="application/pdf")
