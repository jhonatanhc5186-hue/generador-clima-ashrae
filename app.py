import streamlit as st
import pandas as pd
import numpy as np
import requests
import os
import re
import urllib.parse
import streamlit.components.v1 as components
from weasyprint import HTML
from supabase import create_client

st.set_page_config(page_title="Condiciones Climáticas de Diseño", layout="wide", initial_sidebar_state="collapsed")

# --- 1. CONFIGURACIÓN DE CONEXIÓN A SUPABASE ---
SUPABASE_URL = "https://hyzuooqfxthpsftftkza.supabase.co"
SUPABASE_KEY = "sb_publishable_THRgFkbPdniWOjDpZTjU-A_lbeF8A7D"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def verificar_pago_en_db(email):
    try:
        result = supabase.table("pagos").select("*").eq("email", email.strip()).eq("status", "approved").execute()
        return len(result.data) > 0
    except Exception as e:
        st.error(f"Error al conectar con la base de datos de validación: {e}")
        return False

# --- ESTADOS DE SESIÓN ---
if 'lat' not in st.session_state:
    st.session_state.lat = -16.3410
if 'lon' not in st.session_state:
    st.session_state.lon = -71.5830
if 'pagado' not in st.session_state:
    st.session_state.pagado = False

# --- 2. CALLBACK DE BÚSQUEDA GEOGRÁFICA ---
def execute_search():
    st.session_state.pop('search_success', None)
    st.session_state.pop('search_error', None)
    query = st.session_state.get('search_input', '')
    if query:
        clean_query = query.replace(',', ', ').strip()
        safe_query = urllib.parse.quote(clean_query)
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        encontrado = False
        
        # Motor 1: Nominatim
        try:
            url = f"https://nominatim.openstreetmap.org/search?q={safe_query}&format=json&limit=1"
            res = requests.get(url, headers=headers, timeout=5).json()
            if res:
                st.session_state.lat = float(res[0]['lat'])
                st.session_state.lon = float(res[0]['lon'])
                st.session_state.search_success = f"📍 Ubicación confirmada: {res[0]['display_name']}"
                encontrado = True
        except: pass
        
        # Motor 2: Open-Meteo
        if not encontrado:
            try:
                url2 = f"https://geocoding-api.open-meteo.com/v1/search?name={safe_query}&count=1&language=es&format=json"
                res2 = requests.get(url2, timeout=5).json()
                if "results" in res2 and res2["results"]:
                    loc = res2["results"][0]
                    st.session_state.lat = float(loc['latitude'])
                    st.session_state.lon = float(loc['longitude'])
                    name = ", ".join(filter(None, [loc.get('name'), loc.get('admin1'), loc.get('country')]))
                    st.session_state.search_success = f"📍 Ubicación confirmada: {name}"
                    encontrado = True
            except: pass
        
        if not encontrado:
            st.session_state.search_error = "No se encontró la ubicación. Verifique la ortografía o agregue el país."

# --- 3. FUNCIONES BASE ---
def clean_city_name(filename):
    dept_map = {"AMA": "Amazonas", "ANC": "Áncash", "APU": "Apurímac", "ARE": "Arequipa", "AYA": "Ayacucho", "CAJ": "Cajamarca", "CUS": "Cusco", "HUC": "Huánuco", "HUV": "Huancavelica", "ICA": "Ica", "JUN": "Junín", "LAL": "La Libertad", "LAM": "Lambayeque", "LIM": "Lima", "LOR": "Loreto", "MDD": "Madre de Dios", "MOQ": "Moquegua", "PAS": "Pasco", "PIU": "Piura", "PUN": "Puno", "SAM": "San Martín", "TAC": "Tacna", "TUM": "Tumbes", "UCA": "Ucayali"}
    try:
        parts = filename.split('_')
        if len(parts) >= 3:
            pais = "Perú" if parts[0] == "PER" else parts[0]
            departamento = dept_map.get(parts[1], parts[1])
            ciudad = " ".join(parts[2].split('.')[:-1]).split('-')[0].strip()
            if ciudad == "Tacna": departamento = "Tacna"
            if ciudad == "Ilo": departamento = "Moquegua"
            return f"{pais} - {departamento} - {ciudad}"
        return filename.replace(".epw", "")
    except: return filename

def get_epw_mapping():
    if not os.path.exists("data"): return {}
    return {clean_city_name(f): f for f in sorted([f for f in os.listdir("data") if f.endswith(".epw")])}

def format_coord(val, is_lat):
    try: return f"{abs(float(val)):.4f}{'N' if float(val) >= 0 else 'S'}" if is_lat else f"{abs(float(val)):.4f}{'E' if float(val) >= 0 else 'W'}"
    except: return str(val)

def get_location_name(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, timeout=5).json()
        address = res.get('address', {})
        pais = address.get('country', 'PERÚ').upper()
        ciudad = address.get('city', address.get('town', address.get('village', address.get('county', 'UBICACIÓN DESCONOCIDA')))).upper()
        return f"{ciudad}, {pais}"
    except: return f"LAT: {lat}, LON: {lon}"

# --- 4. MOTOR TERMODINÁMICO LOCAL ---
def calc_wb(T, RH):
    return T * np.arctan(0.151977 * (RH + 8.313659)**0.5) + np.arctan(T + RH) - np.arctan(RH - 1.676331) + 0.00391838 * (RH)**1.5 * np.arctan(0.023101 * RH) - 4.686035

def calc_enthalpy(T, HR):
    return 1.006 * T + (HR/1000) * (2501 + 1.86 * T)

def mc(sub, base_col, target_col, t):
    h = sub[(sub[base_col] >= t - 0.2) & (sub[base_col] <= t + 0.2)]
    return h[target_col].mean() if not h.empty else sub[target_col].mean()

def fmt_u(v, decimals=1):
    if pd.isna(v) or v in ('N/A', '', None): return 'N/A'
    try:
        if np.isinf(float(v)): return 'N/A'
        return f"{float(v):.{decimals}f}"
    except: return str(v)

# --- 5. INTERFAZ PROFESIONAL ---
st.markdown("<h2 style='text-align: center; color: #1f456e; font-family: Arial, sans-serif; font-weight: bold;'>CONDICIONES CLIMÁTICAS DE DISEÑO</h2>", unsafe_allow_html=True)
st.markdown("---")

col_params, col_map = st.columns([1, 2.5], gap="large")

with col_params:
    st.markdown("<h4 style='color: #333; font-family: Arial, sans-serif;'>Configuración del Reporte</h4>", unsafe_allow_html=True)
    modo = st.radio("Fuente de Datos:", ["Coordenadas Satelitales (NASA)", "Estación Local (Datos EPW)"], label_visibility="collapsed")
    
    st.markdown("<hr style='margin: 15px 0;'>", unsafe_allow_html=True)
    file_map = get_epw_mapping()

    if "Satelitales" in modo:
        usar_local = False
        st.selectbox("Tipo de Reporte", ["Condiciones Climáticas de Diseño"], disabled=True)
        lat = st.number_input("Latitud", format="%.4f", key="lat")
        lon = st.number_input("Longitud", format="%.4f", key="lon")
        start_y = st.selectbox("Año de Inicio", list(range(2001, 2020)), index=3) 
        end_y = st.selectbox("Año de Fin", list(range(2006, 2025)), index=18)    
    else:
        usar_local = True
        if not file_map:
            st.warning("No se encontraron archivos .epw en la carpeta data.")
            selected_city = None
        else:
            selected_city = st.selectbox("Seleccionar Estación (Local EPW)", list(file_map.keys()))
            filename = file_map[selected_city]
            try:
                with open(f"data/{filename}", 'r', encoding='utf-8') as f:
                    h_data = f.readline().split(',')
                    st.session_state.lat = float(h_data[6])
                    st.session_state.lon = float(h_data[7])
            except: pass
        lat = st.number_input("Latitud", format="%.4f", key="lat", disabled=True)
        lon = st.number_input("Longitud", format="%.4f", key="lon", disabled=True)
        start_y, end_y = 2001, 2024

    st.markdown("<br>", unsafe_allow_html=True) 
    
    # --- SISTEMA DE CONTROL DE ACCESO MEDIANTE BASE DE DATOS ---
    btn_generar = False
    MONTO_DISPLAY = "2.00"   
    MONEDA_DISPLAY = "S/"    
    
    if not st.session_state.pagado:
        st.info("🔒 Ingrese el correo electrónico con el que realizó el pago en Mercado Pago para activar las descargas.")
        
        email_usuario = st.text_input("Correo registrado de pago:", placeholder="correo@ejemplo.com")
        
        col_btn_verificar, col_btn_link = st.columns([1, 1])
        
        with col_btn_verificar:
            if st.button("Validar Acceso", use_container_width=True, type="secondary"):
                if email_usuario:
                    with st.spinner("Consultando estado de cuenta..."):
                        if verificar_pago_en_db(email_usuario):
                            st.session_state.pagado = True
                            st.success("¡Pago validado! Acceso concedido.")
                            st.rerun()
                        else:
                            st.error("No se encontró un pago aprobado asociado a este correo.")
                else:
                    st.warning("Por favor ingrese un correo válido.")
                    
        with col_btn_link:
            link_pago_real = "https://mpago.la/1bhrXb7" 
            st.markdown(
                f"""<a href="{link_pago_real}" target="_blank" style="display: block; text-align: center; background-color: #009ee3; color: white; padding: 10px; border-radius: 4px; text-decoration: none; font-weight: bold; font-family: sans-serif; font-size: 13px;">💳 Ir a Pagar ({MONEDA_DISPLAY} {MONTO_DISPLAY})</a>""", 
                unsafe_allow_html=True
            )
    else:
        st.success("✅ Plataforma desbloqueada correctamente.")
        btn_generar = st.button("Generar Reporte Maestro", type="primary", use_container_width=True)

with col_map:
    if not usar_local:
        col_search, col_btn = st.columns([4, 1])
        col_search.text_input("Búsqueda Geográfica:", placeholder="Buscar ciudad (Ej. Ilo, Moquegua)...", label_visibility="collapsed", key="search_input")
        col_btn.button("Buscar y Ubicar", on_click=execute_search, use_container_width=True)
        
        if 'search_success' in st.session_state: st.success(st.session_state.search_success)
        if 'search_error' in st.session_state: st.error(st.session_state.search_error)
    
    # MAPA SATELITAL
    map_html = f"""
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <div style="text-align:right; font-size:12px; color:#555; font-family:Arial; margin-bottom:5px;">Latitud: {st.session_state.lat:.4f} | Longitud: {st.session_state.lon:.4f}</div>
    <div id="map" style="height: 480px; width: 100%; border-radius: 6px; border: 1px solid #ccc;"></div>
    <script>
        var map = L.map('map').setView([{st.session_state.lat}, {st.session_state.lon}], 11);
        L.tileLayer('http://mt0.google.com/vt/lyrs=s,h&x={{x}}&y={{y}}&z={{z}}', {{
            maxZoom: 20,
            attribution: '&copy; Google Maps'
        }}).addTo(map);
        var marker = L.marker([{st.session_state.lat}, {st.session_state.lon}]).addTo(map);
    </script>
    """
    components.html(map_html, height=520)

st.markdown("---")

# --- 6. CSS REPORTE ---
css_base = """
<style>
    @page { size: A4 portrait; margin: 6mm; }
    body { font-family: 'Times New Roman', Times, serif; margin: 0; padding: 0; background-color: #ffffff; color: #000; }
    table { width: 100% !important; border-collapse: collapse !important; margin-bottom: 6px !important; table-layout: fixed !important; border: 1px solid #000; }
    th, td { border: 1px solid black !important; padding: 1px 2px !important; text-align: center !important; line-height: 1.1 !important; word-wrap: break-word !important; }
    .header-blue, th.nasa-blue { background-color: #0000cc !important; color: white !important; font-weight: bold; padding: 2px !important; border: 1px solid #0000cc !important; }
    .gray-header td { font-weight: bold; background-color: #ffffff !important; } 
    .title-bar { text-align: center; font-weight: bold; margin-bottom: 3px; color: #000; }
    .location-pin { text-align: center; font-weight: bold; margin-bottom: 6px; color: #000; }
    a { display: none !important; }
</style>
"""
css_pdf = css_base + "<style> body, td { font-size: 6px !important; } .header-blue, th.nasa-blue { font-size: 7px !important; } .title-bar { font-size: 11px !important; } .location-pin { font-size: 12px !important; } </style>"
css_preview = css_base + "<style> body, td { font-size: 11px !important; } .header-blue, th.nasa-blue { font-size: 13px !important; } .title-bar { font-size: 16px !important; } .location-pin { font-size: 15px !important; } table { margin-bottom: 15px !important; } </style>"

# --- 7. LÓGICA DE GENERACIÓN ---
if btn_generar:
    if start_y >= end_y:
        st.error("Error: El año de inicio debe ser menor al año de fin.")
        st.stop()

    if not usar_local:
        with st.spinner("Procesando matriz satelital nativa en Sistema Internacional (SI)..."):
            api_url = f"https://power.larc.nasa.gov/api/application/indicators/point?start={start_y}&end={end_y}&latitude={lat}&longitude={lon}&format=html&user=DAVE"
            try:
                respuesta = requests.get(api_url, timeout=45)
                if respuesta.status_code == 200:
                    html_crudo = respuesta.text
                    
                    html_crudo = re.sub(r'(?i)https?://power\.larc\.nasa\.gov[^\s<]*', '', html_crudo)
                    html_crudo = re.sub(r'POWER Climatic Design Conditions \(.*?\)', 'CONDICIONES CLIMÁTICAS DE DISEÑO', html_crudo)
                    html_crudo = html_crudo.replace("POWER Climatic Design Conditions", "CONDICIONES CLIMÁTICAS DE DISEÑO")
                    
                    loc_name = get_location_name(lat, lon)
                    pin_html = f"<div class='location-pin'><span style='color: #1f456e;'>📍</span> {loc_name} (WMO: SATELITAL)</div>"
                    html_crudo = html_crudo.replace("<table", f"{pin_html}\n<table", 1)
                    
                    html_preview_final = html_crudo.replace("</head>", "{css}</head>".format(css=css_preview))
                    html_pdf_final = html_crudo.replace("</head>", "{css}</head>".format(css=css_pdf))
                    
                    st.success("Reporte satelital generado de forma nativa exitosamente.")
                    with st.expander("Resultados del Reporte de Diseño (SI)", expanded=True):
                        components.html(html_preview_final, height=700, scrolling=True)
                    
                    pdf_file = HTML(string=html_pdf_final).write_pdf()
                    st.download_button(label="Descargar Reporte en PDF", data=pdf_file, file_name=f"Condiciones_Climaticas_NASA_SI_{lat}_{lon}.pdf", mime="application/pdf")
                elif respuesta.status_code == 422:
                    st.error("Error: Rango de años insuficiente.")
                else:
                    st.error(f"Error de conectividad (HTTP {respuesta.status_code}).")
            except:
                st.error("Error: Tiempo de espera agotado con la NASA.")

    else:
        with st.spinner("Procesando matriz de datos locales y estructurando diseño..."):
            filename = file_map[selected_city]
            period_display = "TMYx"
            try:
                for p in filename.replace(".epw", "").split('.'):
                    if "-" in p and len(p) == 9 and p.split('-')[0].isdigit(): period_display = p
                with open(f"data/{filename}", 'r', encoding='utf-8') as f:
                    h_data = f.readline().split(',')
                    wmo_display = h_data[5].strip()
                    lat_val, lon_val, alt_display = float(h_data[6]), float(h_data[7]), float(h_data[9].strip())
            except: 
                wmo_display, lat_val, lon_val, alt_display = "000000", 0, 0, 0

            df = pd.read_csv(f"data/{filename}", skiprows=8, header=None, usecols=[1,2,3,6,7,8,9,13,14,15,21,33], names=['Month','Day','Hour','DB','DP','RH','Press','GloHorz','DirNorm','DifHorz','WS','Precip'])
            df['Press_kPa'] = df['Press'] / 1000
            df['Precip'] = pd.to_numeric(df['Precip'], errors='coerce').fillna(0).apply(lambda x: 0 if x > 900 else x)
            df['Year'] = 2024
            
            df['Pv'] = 0.61078 * np.exp(17.27 * df['DP'] / (df['DP'] + 237.3))
            df['HR'] = 1000 * 0.62198 * df['Pv'] / (df['Press_kPa'] - df['Pv']) 
            df['Enth'] = calc_enthalpy(df['DB'], df['HR'])
            df['WB'] = calc_wb(df['DB'], df['RH'])

            stdp_display = f"{df['Press_kPa'].mean():.2f} kPa"
            alt_print = f"{alt_display:.1f} m"
            
            hottest_month = df.groupby('Month')['DB'].mean().idxmax()
            coldest_month = df.groupby('Month')['DB'].mean().idxmin()

            all_data = [df] + [df[df['Month'] == m] for m in range(1, 13)]
            
            def build_row(headers, func):
                r = "<tr>"
                for text, rs, cs, is_bold in headers:
                    weight = "bold" if is_bold else "normal"
                    r += f"<td rowspan='{rs}' colspan='{cs}' style='font-weight:{weight};'>{text}</td>"
                vals = [func(d) if not d.empty else 0 for d in all_data]
                for v in vals: r += f"<td>{fmt_u(v)}</td>"
                r += "</tr>"
                return r

            m_rows = ""
            m_rows += build_row([("Temperatures,<br>Degree-Days and<br>Degree-Hours<br>(°C)", 8, 1, True), ("DBAvg", 1, 2, False)], lambda x: x['DB'].mean())
            m_rows += build_row([("DBStd", 1, 2, False)], lambda x: x['DB'].std())
            m_rows += build_row([("HDD10.0", 1, 2, False)], lambda x: (10.0 - x['DB']).clip(lower=0).sum() / 24)
            m_rows += build_row([("HDD18.3", 1, 2, False)], lambda x: (18.3 - x['DB']).clip(lower=0).sum() / 24)
            m_rows += build_row([("CDD10.0", 1, 2, False)], lambda x: (x['DB'] - 10.0).clip(lower=0).sum() / 24)
            m_rows += build_row([("CDD18.3", 1, 2, False)], lambda x: (x['DB'] - 18.3).clip(lower=0).sum() / 24)
            m_rows += build_row([("CDH23.3", 1, 2, False)], lambda x: (x['DB'] - 23.3).clip(lower=0).sum())
            m_rows += build_row([("CDH26.7", 1, 2, False)], lambda x: (x['DB'] - 26.7).clip(lower=0).sum())
            
            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([("Wind (m/s)", 1, 1, True), ("WSAvg", 1, 2, False)], lambda x: x['WS'].mean())
            
            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([("Precipitation<br>(mm)", 4, 1, True), ("PrecAvg", 1, 2, False)], lambda x: x['Precip'].sum())
            m_rows += build_row([("PrecMax", 1, 2, False)], lambda x: x['Precip'].sum()) 
            m_rows += build_row([("PrecMin", 1, 2, False)], lambda x: x['Precip'].sum()) 
            m_rows += build_row([("PrecStd", 1, 2, False)], lambda x: 0.0)
            
            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([("Monthly Design<br>Dry Bulb and Mean<br>Coincident Wet<br>Bulb Temperatures<br>(°C)", 8, 1, True), ("0.4%", 2, 1, False), ("DB", 1, 1, False)], lambda x: x['DB'].quantile(0.996))
            m_rows += build_row([("MCWB", 1, 1, False)], lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.996)))
            m_rows += build_row([("2%", 2, 1, False), ("DB", 1, 1, False)], lambda x: x['DB'].quantile(0.980))
            m_rows += build_row([("MCWB", 1, 1, False)], lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.980)))
            m_rows += build_row([("5%", 2, 1, False), ("DB", 1, 1, False)], lambda x: x['DB'].quantile(0.950))
            m_rows += build_row([("MCWB", 1, 1, False)], lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.950)))
            m_rows += build_row([("10%", 2, 1, False), ("DB", 1, 1, False)], lambda x: x['DB'].quantile(0.900))
            m_rows += build_row([("MCWB", 1, 1, False)], lambda x: mc(x, 'DB', 'WB', x['DB'].quantile(0.900)))

            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([("Monthly Design<br>Wet Bulb and Mean<br>Coincident Dry<br>Bulb Temperatures<br>(°C)", 8, 1, True), ("0.4%", 2, 1, False), ("WB", 1, 1, False)], lambda x: x['WB'].quantile(0.996))
            m_rows += build_row([("MCDB", 1, 1, False)], lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.996)))
            m_rows += build_row([("2%", 2, 1, False), ("WB", 1, 1, False)], lambda x: x['WB'].quantile(0.980))
            m_rows += build_row([("MCDB", 1, 1, False)], lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.980)))
            m_rows += build_row([("5%", 2, 1, False), ("WB", 1, 1, False)], lambda x: x['WB'].quantile(0.950))
            m_rows += build_row([("MCDB", 1, 1, False)], lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.950)))
            m_rows += build_row([("10%", 2, 1, False), ("WB", 1, 1, False)], lambda x: x['WB'].quantile(0.900))
            m_rows += build_row([("MCDB", 1, 1, False)], lambda x: mc(x, 'WB', 'DB', x['WB'].quantile(0.900)))

            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([("Mean Daily<br>Temperature Range<br>(°C)", 5, 1, True), ("MDBR", 1, 2, False)], lambda x: (x.groupby(x.index // 24)['DB'].max() - x.groupby(x.index // 24)['DB'].min()).mean())
            m_rows += build_row([("5% DB", 2, 1, False), ("MCDBR", 1, 1, False)], lambda x: (x.groupby(x.index // 24)['DB'].max() - x.groupby(x.index // 24)['DB'].min()).quantile(0.95))
            m_rows += build_row([("MCWBR", 1, 1, False)], lambda x: (x.groupby(x.index // 24)['WB'].max() - x.groupby(x.index // 24)['WB'].min()).mean())
            m_rows += build_row([("5% WB", 2, 1, False), ("MCDBR", 1, 1, False)], lambda x: (x.groupby(x.index // 24)['DB'].max() - x.groupby(x.index // 24)['DB'].min()).mean())
            m_rows += build_row([("MCWBR", 1, 1, False)], lambda x: (x.groupby(x.index // 24)['WB'].max() - x.groupby(x.index // 24)['WB'].min()).quantile(0.95))

            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([("Clear Sky Solar<br>Irradiance (W m-2)", 2, 1, True), ("Ebn,noon", 1, 2, False)], lambda x: x[x['Hour'].between(11,13)]['DirNorm'].mean() if not x.empty else 0)
            m_rows += build_row([("Edn,noon", 1, 2, False)], lambda x: x[x['Hour'].between(11,13)]['DifHorz'].mean() if not x.empty else 0)
            
            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([("All-Sky Solar<br>Radiation (W m-2)", 2, 1, True), ("RadAvg", 1, 2, False)], lambda x: x['GloHorz'].mean() * 24 / 1000 if not x.empty else 0)
            m_rows += build_row([("RadStd", 1, 2, False)], lambda x: x['GloHorz'].std() * 24 / 1000 if not x.empty else 0)

            city_only = selected_city.split('-')[-1].strip().upper()
            pin_html = f"<div class='location-pin'><span style='color: #1f456e;'>📍</span> {city_only}, PERÚ (WMO: {wmo_display})</div>"

            html_base = f"""
            <html><head></head>
            <body>
                <div class="title-bar">CONDICIONES CLIMÁTICAS DE DISEÑO</div>
                {pin_html}
                
                <table style="border:none; border-top:1.5px solid #000; border-bottom:1.5px solid #000; margin-bottom:5px;">
                    <tr>
                        <td style="border:none; text-align:left;"><b>Latitude:</b> {format_coord(lat_val, True)}</td>
                        <td style="border:none; text-align:left;"><b>Longitude:</b> {format_coord(lon_val, False)}</td>
                        <td style="border:none; text-align:left;"><b>Elevation:</b> {alt_print}</td>
                        <td style="border:none; text-align:left;"><b>StdPres:</b> {stdp_display}</td>
                        <td style="border:none; text-align:left;"><b>Time Zone:</b> -5.0</td>
                        <td style="border:none; text-align:left;"><b>Time Period:</b> {period_display}</td>
                        <td style="border:none; text-align:right;">Note: Local EPW Data</td>
                    </tr>
                </table>

                <table>
                    <tr><th colspan="15" class="header-blue">Annual Heating and Humidification Design Conditions</th></tr>
                    <tr class="gray-header">
                        <td rowspan="2">Coldest<br>Month</td>
                        <td colspan="2">Heating DB (°C)</td>
                        <td colspan="6">Humidification DP / MCDB (°C) and HR (g/kg)</td>
                        <td colspan="4">Coldest month WS / MCDB (m/s / °C)</td>
                        <td colspan="2">MCWS (m/s) / PCWD to<br>99.6% DB</td>
                    </tr>
                    <tr class="gray-header">
                        <td>99.6%</td><td>99%</td>
                        <td>99.6% DP</td><td>HR</td><td>MCDB</td>
                        <td>99% DP</td><td>HR</td><td>MCDB</td>
                        <td>0.4% WS</td><td>MCDB</td><td>1% WS</td><td>MCDB</td>
                        <td>MCWS</td><td>PCWD</td>
                    </tr>
                    <tr>
                        <td style="font-weight:bold;">{coldest_month}</td>
                        <td>{df['DB'].quantile(0.004):.1f}</td><td>{df['DB'].quantile(0.010):.1f}</td>
                        <td>{df['DP'].quantile(0.004):.1f}</td><td>{mc(df, 'DP', 'HR', df['DP'].quantile(0.004)):.1f}</td><td>{mc(df, 'DP', 'DB', df['DP'].quantile(0.004)):.1f}</td>
                        <td>{df['DP'].quantile(0.010):.1f}</td><td>{mc(df, 'DP', 'HR', df['DP'].quantile(0.010)):.1f}</td><td>{mc(df, 'DP', 'DB', df['DP'].quantile(0.010)):.1f}</td>
                        <td>{df['WS'].quantile(0.996):.1f}</td><td>{mc(df, 'WS', 'DB', df['WS'].quantile(0.996)):.1f}</td>
                        <td>{df['WS'].quantile(0.990):.1f}</td><td>{mc(df, 'WS', 'DB', df['WS'].quantile(0.990)):.1f}</td>
                        <td>{mc(df, 'DB', 'WS', df['DB'].quantile(0.004)):.1f}</td><td>N/A</td>
                    </tr>
                </table>

                <table>
                    <tr><th colspan="17" class="header-blue">Annual Cooling, Dehumidification, and Enthalpy Design Conditions</th></tr>
                    <tr class="gray-header">
                        <td rowspan="2">Hottest<br>Month</td><td rowspan="2">Hottest<br>Month<br>DB Range</td>
                        <td colspan="4">Cooling DB / MCWB (°C)</td>
                        <td colspan="4">Evaporation WB / MCDB (°C)</td>
                        <td colspan="3">Dehumid. DP/MCDB (°C) and HR (g/kg)</td>
                        <td colspan="3">Enthalpy / MCDB (kJ/kg / °C)</td>
                        <td rowspan="2">Ext.<br>Max WB<br>(°C)</td>
                    </tr>
                    <tr class="gray-header">
                        <td colspan="2">0.4%</td><td colspan="2">2%</td>
                        <td colspan="2">0.4%</td><td colspan="2">2%</td>
                        <td>0.4% DP</td><td>HR</td><td>MCDB</td>
                        <td>0.4% Enth</td><td>1% Enth</td><td>MCDB</td>
                    </tr>
                    <tr>
                        <td style="font-weight:bold;">{hottest_month}</td>
                        <td>{df[df['Month'] == hottest_month]['DB'].max() - df[df['Month'] == hottest_month]['DB'].min():.1f}</td>
                        <td>{df['DB'].quantile(0.996):.1f}</td><td>{mc(df, 'DB', 'WB', df['DB'].quantile(0.996)):.1f}</td>
                        <td>{df['DB'].quantile(0.980):.1f}</td><td>{mc(df, 'DB', 'WB', df['DB'].quantile(0.980)):.1f}</td>
                        <td>{df['WB'].quantile(0.996):.1f}</td><td>{mc(df, 'WB', 'DB', df['WB'].quantile(0.996)):.1f}</td>
                        <td>{df['WB'].quantile(0.980):.1f}</td><td>{mc(df, 'WB', 'DB', df['WB'].quantile(0.980)):.1f}</td>
                        <td>{df['DP'].quantile(0.996):.1f}</td><td>{mc(df, 'DP', 'HR', df['DP'].quantile(0.996):.1f}</td><td>{mc(df, 'DP', 'DB', df['DP'].quantile(0.996)):.1f}</td>
                        <td>{df['Enth'].quantile(0.996):.1f}</td><td>{df['Enth'].quantile(0.990):.1f}</td><td>{mc(df, 'Enth', 'DB', df['Enth'].quantile(0.996)):.1f}</td>
                        <td>{df['WB'].max():.1f}</td>
                    </tr>
                </table>

                <table>
                    <tr><th colspan="12" class="header-blue">Extreme Annual Design Conditions</th></tr>
                    <tr class="gray-header">
                        <td colspan="3">Extreme Annual WS (m/s)</td><td colspan="4">Extreme Annual Temperature (°C)</td>
                        <td colspan="4">n-Year Return Period Values of Extreme Temperature (°C)</td>
                    </tr>
                    <tr class="gray-header">
                        <td>1%</td><td>2.5%</td><td>5%</td>
                        <td>DB Mean Min/Max</td><td>Standard dev</td><td>WB Mean Min/Max</td><td>Standard dev</td>
                        <td>n=5 years</td><td>n=10 years</td><td>n=20 years</td><td>n=50 years</td>
                    </tr>
                    <tr>
                        <td>{df['WS'].quantile(0.990):.1f}</td><td>{df['WS'].quantile(0.975):.1f}</td><td>{df['WS'].quantile(0.950):.1f}</td>
                        <td>{df['DB'].min():.1f} / {df['DB'].max():.1f}</td><td>{df['DB'].std():.1f}</td>
                        <td>{df['WB'].min():.1f} / {df['WB'].max():.1f}</td><td>{df['WB'].std():.1f}</td>
                        <td>N/A</td><td>N/A</td><td>N/A</td><td>N/A</td>
                    </tr>
                </table>

                <table>
                    <tr><th colspan="16" class="header-blue">Monthly Climatic Design Conditions</th></tr>
                    <tr class="gray-header">
                        <td colspan="3">Parameters</td>
                        <td>Annual</td><td>Jan</td><td>Feb</td><td>Mar</td><td>Apr</td><td>May</td><td>Jun</td>
                        <td>Jul</td><td>Aug</td><td>Sep</td><td>Oct</td><td>Nov</td><td>Dec</td>
                    </tr>
                    {m_rows}
                </table>
            </body></html>
            """
            
            html_preview_final = html_base.replace("</head>", "{css}</head>".format(css=css_preview))
            html_pdf_final = html_base.replace("</head>", "{css}</head>".format(css=css_pdf))
            
            st.success(f"Reporte procesado exitosamente en formato SI.")
            
            with st.expander("Resultados del Reporte de Diseño", expanded=True):
                components.html(html_preview_final, height=700, scrolling=True)
            
            safe_city = re.sub(r"[^A-Za-z0-9_-]+", "_", selected_city).strip("_")
            pdf_file = HTML(string=html_pdf_final).write_pdf()
            st.download_button(label="Descargar Reporte en PDF", data=pdf_file, file_name=f"Condiciones_Climaticas_EPW_SI_{safe_city}.pdf", mime="application/pdf")
