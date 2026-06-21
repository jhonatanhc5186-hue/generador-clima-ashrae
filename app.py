import streamlit as st
import pandas as pd
import requests
from weasyprint import HTML

# Configuración de la página
st.set_page_config(page_title="Generador ASHRAE", layout="wide")
st.title("🌍 Generador de Reportes Climáticos ASHRAE")

# Inputs de usuario
col1, col2, col3 = st.columns(3)
lat = col1.number_input("Latitud", value=-9.5822, format="%.4f")
lon = col2.number_input("Longitud", value=-77.0234, format="%.4f")
year = col3.selectbox("Año:", list(range(2024, 2014, -1)))

if st.button("Generar Reporte"):
    with st.spinner("Descargando datos y calculando ASHRAE..."):
        # 1. Obtener datos NASA
        url = f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M,T2MWET&community=SB&longitude={lon}&latitude={lat}&start={year}0101&end={year}1231&format=JSON"
        res = requests.get(url).json()
        
        # Datos extraídos
        alt = round(res['geometry']['coordinates'][2], 1)
        t2m = res['properties']['parameter']['T2M']
        t2m_wet = res['properties']['parameter']['T2MWET']
        
        # Crear DataFrame
        dates = pd.date_range(start=f"{year}-01-01", periods=len(t2m), freq='h')
        df = pd.DataFrame({'Date': dates, 'DB': list(t2m.values()), 'WB': list(t2m_wet.values())})
        df['Month'] = df['Date'].dt.month
        df['Day'] = df['Date'].dt.date
        
        # 2. Cálculos Estadísticos
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
            mean_daily_range_c = (daily_max - daily_min).mean()
            
            def calc_mcwb(sub, t):
                h = sub[(sub['DB'] >= t - 0.5) & (sub['DB'] <= t + 0.5)]
                return h['WB'].mean() if not h.empty else sub['WB'].max()
            
            c_to_f = lambda c: (c * 9/5) + 32
            
            data_rows.append({
                'Mes': meses[m-1],
                'DB_04_C': db_04, 'DB_04_F': c_to_f(db_04),
                'MCWB_04_C': calc_mcwb(df_m, db_04), 'MCWB_04_F': c_to_f(calc_mcwb(df_m, db_04)),
                'DB_20_C': db_20, 'DB_20_F': c_to_f(db_20),
                'MCWB_20_C': calc_mcwb(df_m, db_20), 'MCWB_20_F': c_to_f(calc_mcwb(df_m, db_20)),
                'Heat_996_C': db_996, 'Heat_996_F': c_to_f(db_996),
                'Heat_990_C': db_990, 'Heat_990_F': c_to_f(db_990),
                'Range_C': mean_daily_range_c, 'Range_F': mean_daily_range_c * 9/5
            })

        # 3. Construir filas de tabla HTML
        filas = ""
        for r in data_rows:
            filas += f"<tr><td>{r['Mes']}</td><td>{r['DB_04_C']:.1f}</td><td>{r['DB_04_F']:.1f}</td><td>{r['MCWB_04_C']:.1f}</td><td>{r['MCWB_04_F']:.1f}</td><td>{r['DB_20_C']:.1f}</td><td>{r['DB_20_F']:.1f}</td><td>{r['MCWB_20_C']:.1f}</td><td>{r['MCWB_20_F']:.1f}</td><td>{r['Heat_996_C']:.1f}</td><td>{r['Heat_996_F']:.1f}</td><td>{r['Heat_990_C']:.1f}</td><td>{r['Heat_990_F']:.1f}</td><td>{r['Range_C']:.1f}</td><td>{r['Range_F']:.1f}</td></tr>"

        # 4. Generar PDF
        html = f"<html><body><h1>Reporte ASHRAE</h1><table border='1'>{filas}</table></body></html>"
        pdf_data = HTML(string=html).write_pdf()
        
        st.success("¡Calculado!")
        st.download_button("📥 Descargar PDF", data=pdf_data, file_name="reporte.pdf", mime="application/pdf")
