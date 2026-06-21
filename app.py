import streamlit as st
import pandas as pd
import requests
from weasyprint import HTML
import io

st.set_page_config(page_title="Generador ASHRAE", layout="wide")
st.title("🌍 Generador de Reportes Climáticos ASHRAE")

# Inputs del usuario
col1, col2, col3 = st.columns(3)
lat = col1.number_input("Latitud", value=-13.71, format="%.4f")
lon = col2.number_input("Longitud", value=-76.21, format="%.4f")
year = col3.selectbox("Año de análisis:", list(range(2024, 2014, -1)))

if st.button("Generar Reporte"):
    with st.spinner("Consultando datos de la NASA..."):
        # 1. Obtención de datos
        url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET&community=SB&longitude={lon}&latitude={lat}&start={year}0101&end={year}1231&format=JSON"
        res = requests.get(url).json()
        
        # 2. Procesamiento
        t2m = res['properties']['parameter']['T2M']
        t2m_wet = res['properties']['parameter']['T2MWET']
        df = pd.DataFrame({'DB': list(t2m.values()), 'WB': list(t2m_wet.values())})
        df['Month'] = pd.date_range(start=f"{year}-01-01", periods=len(df), freq='h').month
        
        # Aquí iría tu lógica de cálculo (calculamos de forma simplificada para el ejemplo)
        # ... (puedes copiar aquí el bloque de cálculos que ya teníamos) ...
        
        # 3. Generación del HTML para PDF
        html_content = "<h1>Reporte Climático</h1><p>Datos calculados exitosamente.</p>" 
        
        # 4. Crear PDF en memoria
        pdf_file = HTML(string=html_content).write_pdf()
        
        st.success("¡Reporte listo!")
        st.download_button(
            label="📥 Descargar Reporte PDF",
            data=pdf_file,
            file_name=f"Reporte_Clima_{lat}_{lon}.pdf",
            mime="application/pdf"
        )
