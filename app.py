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
    with st.spinner("Procesando datos y dibujando PDF..."):
        # --- Lógica de cálculo ---
        url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET&community=SB&longitude={lon}&latitude={lat}&start={year}0101&end={year}1231&format=JSON"
        res = requests.get(url).json()
        t2m = res['properties']['parameter']['T2M']
        t2m_wet = res['properties']['parameter']['T2MWET']
        df = pd.DataFrame({'DB': list(t2m.values()), 'WB': list(t2m_wet.values())})
        df['Month'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').month
        
        data_rows = []
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        
        for m in range(1, 13):
            df_m = df[df['Month'] == m]
            db_04 = df_m['DB'].quantile(0.996)
            db_20 = df_m['DB'].quantile(0.980)
            data_rows.append({'Mes': meses[m-1], 'DB_04': db_04, 'DB_20': db_20})

        # --- Construcción del HTML con datos reales ---
        filas_html = "".join([f"<tr><td>{r['Mes']}</td><td>{r['DB_04']:.1f}</td><td>{r['DB_20']:.1f}</td></tr>" for r in data_rows])
        
        html_final = f"""
        <html>
        <body>
            <h1>Reporte ASHRAE</h1>
            <table border="1">
                <tr><th>Mes</th><th>DB 0.4%</th><th>DB 2.0%</th></tr>
                {filas_html}
            </table>
        </body>
        </html>
        """
        
        # --- Generar PDF ---
        pdf_file = HTML(string=html_final).write_pdf()
        
        st.success("¡Datos cargados correctamente!")
        st.download_button("📥 Descargar PDF", data=pdf_file, file_name="reporte_final.pdf", mime="application/pdf")
