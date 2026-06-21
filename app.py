import streamlit as st
import pandas as pd
import requests
import io
from weasyprint import HTML

st.set_page_config(page_title="Generador ASHRAE", layout="wide")
st.title("🌍 Generador de Reportes Climáticos ASHRAE")

col1, col2, col3 = st.columns(3)
lat = col1.number_input("Latitud", value=-9.5822, format="%.4f")
lon = col2.number_input("Longitud", value=-77.0234, format="%.4f")
year = col3.selectbox("Año de análisis:", list(range(2024, 2014, -1)))

if st.button("Generar Reporte"):
    with st.spinner("Procesando datos ASHRAE..."):
        # 1. Obtención de datos NASA
        url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET&community=SB&longitude={lon}&latitude={lat}&start={year}0101&end={year}1231&format=JSON"
        res = requests.get(url).json()
        
        t2m = res['properties']['parameter']['T2M']
        t2m_wet = res['properties']['parameter']['T2MWET']
        
        df = pd.DataFrame({'DB': list(t2m.values()), 'WB': list(t2m_wet.values())})
        df['Month'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').month
        
        # 2. Tu lógica de cálculo ASHRAE
        data_rows = []
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        
        for m in range(1, 13):
            df_m = df[df['Month'] == m]
            db_04 = df_m['DB'].quantile(0.996)
            data_rows.append({'Mes': meses[m-1], 'DB_04': db_04}) # Simplificado para el ejemplo
            
        # 3. Generación del HTML (Aquí pegas tu bloque de HTML que ya tienes)
        html_content = "<h1>Reporte Climático</h1><p>Resultados calculados.</p>" 
        # (Usa aquí el string largo que ya tenías en tu script de Colab)
        
        # 4. Crear PDF
        pdf_file = HTML(string=html_content).write_pdf()
        
        st.success("¡Reporte generado exitosamente!")
        st.download_button("📥 Descargar PDF", data=pdf_file, file_name="reporte_ashrae.pdf", mime="application/pdf")
