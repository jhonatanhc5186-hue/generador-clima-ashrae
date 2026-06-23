import streamlit as st
import pandas as pd
import numpy as np
import requests
import os
import re
import urllib.parse
import streamlit.components.v1 as components
from weasyprint import HTML
from bs4 import BeautifulSoup

st.set_page_config(page_title="Condiciones Climáticas de Diseño", layout="wide", initial_sidebar_state="collapsed")

# --- 1. ESTADOS DE SESIÓN (MAPA, COORDENADAS Y PAGOS) ---
if 'lat' not in st.session_state:
    st.session_state.lat = -16.3410
if 'lon' not in st.session_state:
    st.session_state.lon = -71.5830
if 'pagado' not in st.session_state:
    st.session_state.pagado = False

# Detectar retorno exitoso desde la pasarela de pago (Stripe)
if "pago" in st.query_params and st.query_params["pago"] == "exitoso":
    st.session_state.pagado = True

# --- 2. FUNCIONES BASE ---
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
        res = requests.get(url, headers={'User-Agent': 'AppPeruClima/1.0'}, timeout=10).json()
        address = res.get('address', {})
        pais = address.get('country', 'PERÚ').upper()
        ciudad = address.get('city', address.get('town', address.get('village', address.get('county', 'UBICACIÓN DESCONOCIDA')))).upper()
        return f"{ciudad}, {pais}"
    except: return f"LAT: {lat}, LON: {lon}"

# --- 3. MOTOR TERMODINÁMICO Y CONVERSIÓN ---
def calc_wb(T, RH):
    return T * np.arctan(0.151977 * (RH + 8.313659)**0.5) + np.arctan(T + RH) - np.arctan(RH - 1.676331) + 0.00391838 * (RH)**1.5 * np.arctan(0.023101 * RH) - 4.686035

def calc_enthalpy(T, HR):
    return 1.006 * T + (HR/1000) * (2501 + 1.86 * T)

def mc(sub, base_col, target_col, t):
    h = sub[(sub[base_col] >= t - 0.2) & (sub[base_col] <= t + 0.2)]
    return h[target_col].mean() if not h.empty else sub[target_col].mean()

def is_missing(v):
    try: return pd.isna(v)
    except: return False

def apply_u(v, vtype, is_ip):
    if not is_ip: return v
    if v in ('N/A', '', None, '-', '---') or is_missing(v): return np.nan
    try: v = float(v)
    except: return v
    
    if vtype == 'T': return v * 1.8 + 32          
    if vtype == 'TR': return v * 1.8              
    if vtype == 'P': return v / 25.4              
    if vtype == 'WS': return v * 2.23694          
    if vtype == 'E': return v * 0.429923          
    if vtype == 'HR': return v * 7.0              
    if vtype == 'R': return v * 0.316998          
    if vtype == 'ALT': return v * 3.28084           
    if vtype == 'PRES': return v * 0.295300          
    return v

def fmt_u(v, decimals=1):
    if v in ('N/A', '', None) or is_missing(v): return 'N/A'
    try:
        if np.isinf(float(v)): return 'N/A'
        return f"{float(v):.{decimals}f}"
    except: return str(v)

def parse_and_convert(text, conv_type, is_ip):
    if not text or not text.strip(): return text
    text = text.strip()
    if text.upper() in ("N/A", "NA", "NULL", "---", "-"): return "N/A"
    parts = re.split(r'\s*/\s*', text)
    converted = []
    for p in parts:
        p = p.strip()
        try:
            val = float(p)
            new_val = apply_u(val, conv_type, is_ip)
            converted.append(fmt_u(new_val))
        except: converted.append(p)
    return " / ".join(converted)

def unit_labels(is_ip):
    return {
        "T": "°F" if is_ip else "°C",
        "P": "in" if is_ip else "mm",
        "WS": "mph" if is_ip else "m/s",
        "R": "Btu/(h·ft²)" if is_ip else "W m-2",
        "HR": "grains/lb" if is_ip else "g/kg",
        "E": "Btu/lb" if is_ip else "kJ/kg",
        "ALT": "ft" if is_ip else "m",
        "PRES": "inHg" if is_ip else "kPa",
    }

# --- 4. INTERFAZ PROFESIONAL ---
st.markdown("<h2 style='text-align: center; color: #1f456e; font-family: Arial, sans-serif; font-weight: bold;'>CONDICIONES CLIMÁTICAS DE DISEÑO</h2>", unsafe_allow_html=True)
st.markdown("---")

col_params, col_map = st.columns([1, 2.5], gap="large")

with col_params:
    st.markdown("<h4 style='color: #333; font-family: Arial, sans-serif;'>Configuración del Reporte</h4>", unsafe_allow_html=True)
    modo = st.radio("Fuente de Datos:", ["Coordenadas Satelitales (NASA)", "Estación Local (Datos EPW)"], label_visibility="collapsed")
    
    st.markdown("<h4 style='color: #333; font-family: Arial, sans-serif; margin-top: 15px;'>Sistema de Unidades</h4>", unsafe_allow_html=True)
    unit_sys = st.radio("Formato:", ["SI (Métrico)", "IP (Imperial)"], horizontal=True, label_visibility="collapsed")
    is_ip = unit_sys == "IP (Imperial)"

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
    
    # --- SISTEMA DE PAYWALL (BOTÓN DE PAGO) ---
    btn_generar = False
    
    if not st.session_state.pagado:
        st.info("🔒 Se requiere autorización de pago para procesar y descargar el reporte de diseño.")
        
        # LINK DE PAGO: Reemplaza esto con tu link real de Stripe / MercadoPago
        link_pago_real = "https://buy.stripe.com/test_tupago" 
        
        col_pay1, col_pay2 = st.columns(2)
        col_pay1.markdown(
            f"""
            <a href="{link_pago_real}" target="_blank" style="display: block; text-align: center; background-color: #0070ba; color: white; padding: 10px; border-radius: 5px; text-decoration: none; font-weight: bold; font-family: Arial;">
                💳 Pagar (Tarjeta)
            </a>
            """, 
            unsafe_allow_html=True
        )
        
        # Botón para que simules pagos mientras pruebas la app
        if col_pay2.button("Simular Pago ✔️"):
            st.session_state.pagado = True
            st.rerun()
    else:
        st.success("✅ Pago validado exitosamente. Acceso desbloqueado.")
        btn_generar = st.button("Generar Reporte Maestro", type="primary", use_container_width=True)

with col_map:
    # BUSCADOR GEOGRÁFICO SÓLO PARA SATÉLITE
    if not usar_local:
        col_search, col_btn = st.columns([4, 1])
        search_text = col_search.text_input("Búsqueda Geográfica:", placeholder="Buscar ciudad (Ej. Arequipa, Perú)...", label_visibility="collapsed")
        if col_btn.button("Buscar y Ubicar", use_container_width=True):
            if search_text:
                try:
                    safe_query = urllib.parse.quote(search_text)
                    url = f"https://geocoding-api.open-meteo.com/v1/search?name={safe_query}&count=1&language=es&format=json"
                    response = requests.get(url, timeout=10)
                    if response.status_code == 200:
                        res = response.json()
                        if "results" in res and len(res["results"]) > 0:
                            loc = res["results"][0]
                            st.session_state.lat = float(loc['latitude'])
                            st.session_state.lon = float(loc['longitude'])
                            parts = [loc.get('name')]
                            if 'admin1' in loc and loc['admin1'] != loc.get('name'): parts.append(loc['admin1'])
                            if 'country' in loc: parts.append(loc['country'])
                            st.success(f"Ubicación confirmada: {', '.join(filter(None, parts))}")
                        else: st.error("No se encontró la ubicación. Verifique la ortografía.")
                    else: st.error("Servidor de mapas saturado.")
                except Exception as e: st.error("Error de conexión con el servidor geográfico.")
    
    # MAPA SATELITAL GOOGLE HYBRID
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

# --- 5. CSS CLÓNICO NASA PARA REPORTES ---
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

units = unit_labels(is_ip)
h_T, h_P, h_WS, h_R, h_HR, h_E = units["T"], units["P"], units["WS"], units["R"], units["HR"], units["E"]
unit_suffix = "IP" if is_ip else "SI"

# --- 6. LÓGICA DE GENERACIÓN MAESTRA ---
if btn_generar:
    if start_y >= end_y:
        st.error("Error: El año de inicio debe ser menor al año de fin.")
        st.stop()

    if not usar_local:
        with st.spinner("Procesando matriz satelital y mapeando conversiones (NASA)..."):
            api_url = f"https://power.larc.nasa.gov/api/application/indicators/point?start={start_y}&end={end_y}&latitude={lat}&longitude={lon}&format=html&user=DAVE"
            try:
                respuesta = requests.get(api_url, timeout=45)
                if respuesta.status_code == 200:
                    html_crudo = respuesta.text
                    
                    html_crudo = re.sub(r'(?i)https?://power\.larc\.nasa\.gov[^\s<]*', '', html_crudo)
                    html_crudo = re.sub(r'POWER Climatic Design Conditions \(.*?\)', 'CONDICIONES CLIMÁTICAS DE DISEÑO', html_crudo)
                    html_crudo = html_crudo.replace("POWER Climatic Design Conditions", "CONDICIONES CLIMÁTICAS DE DISEÑO")
                    
                    if is_ip:
                        try:
                            soup = BeautifulSoup(html_crudo, 'html.parser')
                            
                            # 1. Modificar Textos de Títulos
                            for node in soup.find_all(string=True):
                                if node.parent.name not in ['style', 'script']:
                                    new_text = str(node)
                                    if any(x in new_text for x in ['(°C)', '(m/s)', '(mm)', 'W m-2', 'kJ/kg', 'J/kg', 'g/kg', 'HDD', 'CDD', 'CDH']):
                                        new_text = new_text.replace('(°C)', f'({h_T
