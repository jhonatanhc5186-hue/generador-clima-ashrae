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

# --- 1. ESTADOS DE SESIÓN (MAPA Y COORDENADAS) ---
if 'lat' not in st.session_state:
    st.session_state.lat = -16.3410
if 'lon' not in st.session_state:
    st.session_state.lon = -71.5830

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
    except Exception: return False

def apply_u(v, vtype, is_ip):
    if not is_ip: return v
    if v in ('N/A', '', None) or is_missing(v): return np.nan
    try: v = float(v)
    except Exception: return v
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
    except Exception: return str(v)

def parse_and_convert(text, conv_type, is_ip):
    if not text or not text.strip(): return text
    text = text.strip()
    if text.upper() in ("N/A", "NA"): return "N/A"
    parts = re.split(r'\s*/\s*', text)
    converted = []
    for p in parts:
        p = p.strip()
        try:
            val = float(p)
            new_val = apply_u(val, conv_type, is_ip)
            converted.append(fmt_u(new_val))
        except Exception: converted.append(p)
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

# --- 4. INTERFAZ PROFESIONAL (CONTROLES IZQUIERDA / MAPA DERECHA) ---
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
            except Exception: pass
        lat = st.number_input("Latitud", format="%.4f", key="lat", disabled=True)
        lon = st.number_input("Longitud", format="%.4f", key="lon", disabled=True)
        start_y, end_y = 2001, 2024

    st.markdown("<br>", unsafe_allow_html=True) 
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
                            display_name = ", ".join(filter(None, parts))
                            
                            st.success(f"Ubicación confirmada: {display_name}")
                        else: st.error("No se encontró la ubicación. Intente verificar la ortografía.")
                    else: st.error("Servidor de mapas saturado. Intente de nuevo en unos segundos.")
                except requests.exceptions.Timeout:
                    st.error("El servidor de mapas tardó demasiado en responder.")
                except Exception as e:
                    st.error(f"Error al conectar con el servidor de mapas.")
    
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
h_T = units["T"]
h_P = units["P"]
h_WS = units["WS"]
h_R = units["R"]
h_HR = units["HR"]
h_E = units["E"]
unit_suffix = "IP" if is_ip else "SI"

# --- 6. LÓGICA DE GENERACIÓN ---
if btn_generar:
    if start_y >= end_y:
        st.error("Error: El año de inicio debe ser menor al año de fin.")
        st.stop()

    if not usar_local:
        # =========================================================
        # MODO COORDENADAS: EXTRACCIÓN Y CONVERSIÓN NASA NATIVA
        # =========================================================
        with st.spinner("Procesando matriz de datos satelitales y aplicando conversiones termodinámicas..."):
            api_url = f"https://power.larc.nasa.gov/api/application/indicators/point?start={start_y}&end={end_y}&latitude={lat}&longitude={lon}&format=html&user=DAVE"
            try:
                respuesta = requests.get(api_url, timeout=45)
                if respuesta.status_code == 200:
                    html_crudo = respuesta.text
                    
                    html_crudo = re.sub(r'(?i)https?://power\.larc\.nasa\.gov[^\s<]*', '', html_crudo)
                    html_crudo = re.sub(r'POWER Climatic Design Conditions \(.*?\)', 'CONDICIONES CLIMÁTICAS DE DISEÑO', html_crudo)
                    html_crudo = html_crudo.replace("POWER Climatic Design Conditions", "CONDICIONES CLIMÁTICAS DE DISEÑO")
                    
                    # CONVERSIÓN ESTRUCTURAL QUIRÚRGICA A IP MEDIANTE BEAUTIFUL SOUP
                    if is_ip:
                        try:
                            soup = BeautifulSoup(html_crudo, 'html.parser')
                            
                            # Conversión de unidades en los textos (Cabeceras)
                            for node in soup.find_all(string=True):
                                if node.parent.name not in ['style', 'script']:
                                    new_text = str(node)
                                    if any(x in new_text for x in ['(°C)', '(m/s)', '(mm)', 'W m-2', 'kJ/kg', 'J/kg', 'g/kg', 'HDD', 'CDD', 'CDH']):
                                        new_text = new_text.replace('(°C)', f'({h_T})').replace('(m/s)', f'({h_WS})').replace('(mm)', f'({h_P})')
                                        new_text = new_text.replace('W m-2', h_R).replace('kJ/kg', h_E).replace('J/kg', h_E).replace('g/kg', h_HR)
                                        new_text = new_text.replace('HDD10.0', 'HDD50.0').replace('HDD18.3', 'HDD65.0')
                                        new_text = new_text.replace('CDD10.0', 'CDD50.0').replace('CDD18.3', 'CDD65.0')
                                        new_text = new_text.replace('CDH23.3', 'CDH74.0').replace('CDH26.7', 'CDH80.0')
                                        if new_text != str(node): node.replace_with(new_text)

                            # Conversión de valores numéricos en tablas (Búsqueda por nombre de tabla)
                            for table in soup.find_all('table'):
                                header_text = table.get_text(" ", strip=True)
                                trs = table.find_all('tr')
                                if not trs: continue

                                # Tabla 1: Annual Heating
                                if "Annual Heating and Humidification" in header_text:
                                    try:
                                        tds = trs[-1].find_all('td')
                                        convs = [None, 'T', 'T', 'T', 'HR', 'T', 'T', 'HR', 'T', 'WS', 'T', 'WS', 'T', 'WS', 'WS']
                                        for i, td in enumerate(tds):
                                            if i < len(convs) and convs[i]:
                                                td.string = parse_and_convert(td.get_text(strip=True), convs[i], True)
                                    except Exception: pass

                                # Tabla 2: Annual Cooling
                                elif "Annual Cooling, Dehumidification, and Enthalpy" in header_text:
                                    try:
                                        tds = trs[-1].find_all('td')
                                        if len(tds) >= 17:
                                            convs = [None, 'TR', 'T', 'T', 'T', 'T', 'T', 'T', 'T', 'T', 'T', 'HR', 'T', 'E', 'E', 'T', 'T']
                                            for i, td in enumerate(tds):
                                                if i < len(convs) and convs[i]:
                                                    td.string = parse_and_convert(td.get_text(strip=True), convs[i], True)
                                    except Exception: pass

                                # Tabla 3: Extreme Annual
                                elif "Extreme Annual Design Conditions" in header_text:
                                    try:
                                        for tr in trs[2:]:
                                            tds = tr.find_all('td')
                                            if len(tds) >= 16: # Fila Dry Bulb
                                                convs = ['WS', 'WS', 'WS', None, 'T', 'TR', 'T', 'TR', 'T', 'T', 'T', 'T', 'T', 'T', 'T', 'T']
                                                for i, td in enumerate(tds):
                                                    if i < len(convs) and convs[i]:
                                                        td.string = parse_and_convert(td.get_text(strip=True), convs[i], True)
                                            elif len(tds) >= 13: # Fila Wet Bulb
                                                convs = [None, 'T', 'TR', 'T', 'TR', 'T', 'T', 'T', 'T', 'T', 'T', 'T', 'T']
                                                for i, td in enumerate(tds):
                                                    if i < len(convs) and convs[i]:
                                                        td.string = parse_and_convert(td.get_text(strip=True), convs[i], True)
                                    except Exception: pass

                                # Tabla 4: Monthly Climatic
                                elif "Monthly Climatic Design Conditions" in header_text:
                                    try:
                                        for tr in trs:
                                            tds = tr.find_all(['td', 'th'])
                                            if len(tds) < 13: continue
                                            row_text = tr.get_text(" ", strip=True)
                                            vtype = None
                                            
                                            # Identificación de métrica
                                            if any(x in row_text for x in ['DBAvg', '0.4%', '1%', '2%', '5%', '10%', 'DB', 'WB', 'MCWB', 'MCDB', 'Max WB']): vtype = 'T'
                                            if any(x in row_text for x in ['DBStd', 'MDBR', 'MCDBR', 'MCWBR', 'HDD', 'CDD', 'CDH']): vtype = 'TR'
                                            if 'WSAvg' in row_text: vtype = 'WS'
                                            if 'Prec' in row_text: vtype = 'P'
                                            if any(x in row_text for x in ['Solar', 'Rad', 'Ebn', 'Edn']): vtype = 'R'
                                            
                                            # Procesamos las últimas 13 celdas (Anual + 12 Meses)
                                            if vtype:
                                                for td in tds[-13:]:
                                                    td.string = parse_and_convert(td.get_text(strip=True), vtype, True)
                                    except Exception: pass

                            # Conversión de Elevación y Presión Estándar
                            for td in soup.find_all('td'):
                                txt = td.get_text(" ", strip=True)
                                if txt.startswith("Elevation:"):
                                    m = re.search(r"Elevation:\s*([-+]?\d+(?:\.\d+)?)", txt)
                                    if m:
                                        try: td.string = f"Elevation: {fmt_u(apply_u(float(m.group(1)), 'ALT', True), 1)} {units['ALT']}"
                                        except Exception: pass
                                elif txt.startswith("StdPres:"):
                                    m = re.search(r"StdPres:\s*([-+]?\d+(?:\.\d+)?)", txt)
                                    if m:
                                        try: td.string = f"StdPres: {fmt_u(apply_u(float(m.group(1)), 'PRES', True), 2)} {units['PRES']}"
                                        except Exception: pass
                            
                            html_crudo = str(soup)
                        except Exception: pass

                    # Inserción final del Pin de Ubicación
                    loc_name = get_location_name(lat, lon)
                    pin_html = f"<div class='location-pin'><span style='color: #1f456e;'>📍</span> {loc_name} (WMO: SATELITAL)</div>"
                    html_crudo = html_crudo.replace("<table", f"{pin_html}\n<table", 1)
                    
                    html_preview_final = html_crudo.replace("</head>", "{css}</head>".format(css=css_preview))
                    html_pdf_final = html_crudo.replace("</head>", "{css}</head>".format(css=css_pdf))
                    
                    st.success("Reporte procesado y convertido exitosamente.")
                    with st.expander("Resultados del Reporte de Diseño", expanded=True):
                        components.html(html_preview_final, height=700, scrolling=True)
                    
                    pdf_file = HTML(string=html_pdf_final).write_pdf()
                    st.download_button(label="Descargar Reporte en PDF", data=pdf_file, file_name=f"Condiciones_Climaticas_NASA_{unit_suffix}_{lat}_{lon}.pdf", mime="application/pdf")
                
                elif respuesta.status_code == 422:
                    st.error("Error: El servidor ha rechazado la solicitud debido a un rango de años insuficiente.")
                else: 
                    st.error(f"Error de conectividad (HTTP {respuesta.status_code}).")
            
            except Exception as e: 
                st.error("Error: Tiempo de espera agotado.")

    else:
        # =========================================================
        # MODO EPW LOCAL: CONVERSIÓN Y RENDERIZADO
        # =========================================================
        if not selected_city:
            st.error("Agregue archivos .epw en la carpeta data para usar el modo local.")
            st.stop()

        with st.spinner("Estructurando matriz de datos y procesando diseño..."):
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

            p_kpa = 101.325 * (1 - 2.25577e-5 * alt_display)**5.25588
            stdp_display = f"{p_kpa * 0.2953:.2f} inHg" if is_ip else f"{p_kpa:.2f} kPa"
            alt_print = f"{alt_display * 3.28084:.1f} ft" if is_ip else f"{alt_display} m"
            
            hottest_month = df.groupby('Month')['DB'].mean().idxmax()
            coldest_month = df.groupby('Month')['DB'].mean().idxmin()

            all_data = [df] + [df[df['Month'] == m] for m in range(1, 13)]
            
            def build_row(headers, func):
                r = "<tr>"
                for text, rs, cs, is_bold in headers:
                    weight = "bold" if is_bold else "normal"
                    r += f"<td rowspan='{rs}' colspan='{cs}' style='font-weight:{weight};'>{text}</td>"
                vals = [func(d) if not d.empty else 0 for d in all_data]
                for v in vals:
                    r += f"<td>{fmt_u(v)}</td>"
                r += "</tr>"
                return r

            lab_hdd1, lab_hdd2 = ("HDD50.0", "HDD65.0") if is_ip else ("HDD10.0", "HDD18.3")
            lab_cdd1, lab_cdd2 = ("CDD50.0", "CDD65.0") if is_ip else ("CDD10.0", "CDD18.3")
            lab_cdh1, lab_cdh2 = ("CDH74.0", "CDH80.0") if is_ip else ("CDH23.3", "CDH26.7")

            m_rows = ""
            m_rows += build_row([(f"Temperatures,<br>Degree-Days and<br>Degree-Hours<br>({h_T})", 8, 1, True), ("DBAvg", 1, 2, False)], lambda x: apply_u(x['DB'].mean(), 'T', is_ip))
            m_rows += build_row([("DBStd", 1, 2, False)], lambda x: apply_u(x['DB'].std(), 'TR', is_ip))
            m_rows += build_row([(lab_hdd1, 1, 2, False)], lambda x: apply_u((10.0 - x['DB']).clip(lower=0).sum() / 24, 'TR', is_ip))
            m_rows += build_row([(lab_hdd2, 1, 2, False)], lambda x: apply_u((18.3 - x['DB']).clip(lower=0).sum() / 24, 'TR', is_ip))
            m_rows += build_row([(lab_cdd1, 1, 2, False)], lambda x: apply_u((x['DB'] - 10.0).clip(lower=0).sum() / 24, 'TR', is_ip))
            m_rows += build_row([(lab_cdd2, 1, 2, False)], lambda x: apply_u((x['DB'] - 18.3).clip(lower=0).sum() / 24, 'TR', is_ip))
            m_rows += build_row([(lab_cdh1, 1, 2, False)], lambda x: apply_u((x['DB'] - 23.3).clip(lower=0).sum(), 'TR', is_ip))
            m_rows += build_row([(lab_cdh2, 1, 2, False)], lambda x: apply_u((x['DB'] - 26.7).clip(lower=0).sum(), 'TR', is_ip))
            
            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([(f"Wind ({h_WS})", 1, 1, True), ("WSAvg", 1, 2, False)], lambda x: apply_u(x['WS'].mean(), 'WS', is_ip))
            
            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([(f"Precipitation<br>({h_P})", 4, 1, True), ("PrecAvg", 1, 2, False)], lambda x: apply_u(x['Precip'].sum(), 'P', is_ip))
            m_rows += build_row([("PrecMax", 1, 2, False)], lambda x: apply_u(x['Precip'].sum(), 'P', is_ip)) 
            m_rows += build_row([("PrecMin", 1, 2, False)], lambda x: apply_u(x['Precip'].sum(), 'P', is_ip)) 
            m_rows += build_row([("PrecStd", 1, 2, False)], lambda x: 0.0)
            
            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([(f"Monthly Design<br>Dry Bulb and Mean<br>Coincident Wet<br>Bulb Temperatures<br>({h_T})", 8, 1, True), ("0.4%", 2, 1, False), ("DB", 1, 1, False)], lambda x: apply_u(x['DB'].quantile(0.996), 'T', is_ip))
            m_rows += build_row([("MCWB", 1, 1, False)], lambda x: apply_u(mc(x, 'DB', 'WB', x['DB'].quantile(0.996)), 'T', is_ip))
            m_rows += build_row([("2%", 2, 1, False), ("DB", 1, 1, False)], lambda x: apply_u(x['DB'].quantile(0.980), 'T', is_ip))
            m_rows += build_row([("MCWB", 1, 1, False)], lambda x: apply_u(mc(x, 'DB', 'WB', x['DB'].quantile(0.980)), 'T', is_ip))
            m_rows += build_row([("5%", 2, 1, False), ("DB", 1, 1, False)], lambda x: apply_u(x['DB'].quantile(0.950), 'T', is_ip))
            m_rows += build_row([("MCWB", 1, 1, False)], lambda x: apply_u(mc(x, 'DB', 'WB', x['DB'].quantile(0.950)), 'T', is_ip))
            m_rows += build_row([("10%", 2, 1, False), ("DB", 1, 1, False)], lambda x: apply_u(x['DB'].quantile(0.900), 'T', is_ip))
            m_rows += build_row([("MCWB", 1, 1, False)], lambda x: apply_u(mc(x, 'DB', 'WB', x['DB'].quantile(0.900)), 'T', is_ip))

            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([(f"Monthly Design<br>Wet Bulb and Mean<br>Coincident Dry<br>Bulb Temperatures<br>({h_T})", 8, 1, True), ("0.4%", 2, 1, False), ("WB", 1, 1, False)], lambda x: apply_u(x['WB'].quantile(0.996), 'T', is_ip))
            m_rows += build_row([("MCDB", 1, 1, False)], lambda x: apply_u(mc(x, 'WB', 'DB', x['WB'].quantile(0.996)), 'T', is_ip))
            m_rows += build_row([("2%", 2, 1, False), ("WB", 1, 1, False)], lambda x: apply_u(x['WB'].quantile(0.980), 'T', is_ip))
            m_rows += build_row([("MCDB", 1, 1, False)], lambda x: apply_u(mc(x, 'WB', 'DB', x['WB'].quantile(0.980)), 'T', is_ip))
            m_rows += build_row([("5%", 2, 1, False), ("WB", 1, 1, False)], lambda x: apply_u(x['WB'].quantile(0.950), 'T', is_ip))
            m_rows += build_row([("MCDB", 1, 1, False)], lambda x: apply_u(mc(x, 'WB', 'DB', x['WB'].quantile(0.950)), 'T', is_ip))
            m_rows += build_row([("10%", 2, 1, False), ("WB", 1, 1, False)], lambda x: apply_u(x['WB'].quantile(0.900), 'T', is_ip))
            m_rows += build_row([("MCDB", 1, 1, False)], lambda x: apply_u(mc(x, 'WB', 'DB', x['WB'].quantile(0.900)), 'T', is_ip))

            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([(f"Mean Daily<br>Temperature Range<br>({h_T})", 5, 1, True), ("MDBR", 1, 2, False)], lambda x: apply_u((x.groupby(x.index // 24)['DB'].max() - x.groupby(x.index // 24)['DB'].min()).mean(), 'TR', is_ip))
            m_rows += build_row([("5% DB", 2, 1, False), ("MCDBR", 1, 1, False)], lambda x: apply_u((x.groupby(x.index // 24)['DB'].max() - x.groupby(x.index // 24)['DB'].min()).quantile(0.95), 'TR', is_ip))
            m_rows += build_row([("MCWBR", 1, 1, False)], lambda x: apply_u((x.groupby(x.index // 24)['WB'].max() - x.groupby(x.index // 24)['WB'].min()).mean(), 'TR', is_ip))
            m_rows += build_row([("5% WB", 2, 1, False), ("MCDBR", 1, 1, False)], lambda x: apply_u((x.groupby(x.index // 24)['DB'].max() - x.groupby(x.index // 24)['DB'].min()).mean(), 'TR', is_ip))
            m_rows += build_row([("MCWBR", 1, 1, False)], lambda x: apply_u((x.groupby(x.index // 24)['WB'].max() - x.groupby(x.index // 24)['WB'].min()).quantile(0.95), 'TR', is_ip))

            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([(f"Clear Sky Solar<br>Irradiance ({h_R})", 2, 1, True), ("Ebn,noon", 1, 2, False)], lambda x: apply_u(x[x['Hour'].between(11,13)]['DirNorm'].mean() if not x.empty else 0, 'R', is_ip))
            m_rows += build_row([("Edn,noon", 1, 2, False)], lambda x: apply_u(x[x['Hour'].between(11,13)]['DifHorz'].mean() if not x.empty else 0, 'R', is_ip))
            
            m_rows += "<tr><th colspan='16' class='header-blue'>&nbsp;</th></tr>"
            m_rows += build_row([(f"All-Sky Solar<br>Radiation ({h_R})", 2, 1, True), ("RadAvg", 1, 2, False)], lambda x: apply_u(x['GloHorz'].mean() * 24 / 1000 if not x.empty else 0, 'R', is_ip))
            m_rows += build_row([("RadStd", 1, 2, False)], lambda x: apply_u(x['GloHorz'].std() * 24 / 1000 if not x.empty else 0, 'R', is_ip))

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
                        <td colspan="2">Heating DB ({h_T})</td>
                        <td colspan="6">Humidification DP / MCDB ({h_T}) and HR ({h_HR})</td>
                        <td colspan="4">Coldest month WS / MCDB ({h_WS} / {h_T})</td>
                        <td colspan="2">MCWS ({h_WS}) / PCWD to<br>99.6% DB</td>
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
                        <td>{apply_u(df['DB'].quantile(0.004), 'T', is_ip):.1f}</td><td>{apply_u(df['DB'].quantile(0.010), 'T', is_ip):.1f}</td>
                        <td>{apply_u(df['DP'].quantile(0.004), 'T', is_ip):.1f}</td><td>{apply_u(mc(df, 'DP', 'HR', df['DP'].quantile(0.004)), 'HR', is_ip):.1f}</td><td>{apply_u(mc(df, 'DP', 'DB', df['DP'].quantile(0.004)), 'T', is_ip):.1f}</td>
                        <td>{apply_u(df['DP'].quantile(0.010), 'T', is_ip):.1f}</td><td>{apply_u(mc(df, 'DP', 'HR', df['DP'].quantile(0.010)), 'HR', is_ip):.1f}</td><td>{apply_u(mc(df, 'DP', 'DB', df['DP'].quantile(0.010)), 'T', is_ip):.1f}</td>
                        <td>{apply_u(df['WS'].quantile(0.996), 'WS', is_ip):.1f}</td><td>{apply_u(mc(df, 'WS', 'DB', df['WS'].quantile(0.996)), 'T', is_ip):.1f}</td>
                        <td>{apply_u(df['WS'].quantile(0.990), 'WS', is_ip):.1f}</td><td>{apply_u(mc(df, 'WS', 'DB', df['WS'].quantile(0.990)), 'T', is_ip):.1f}</td>
                        <td>{apply_u(mc(df, 'DB', 'WS', df['DB'].quantile(0.004)), 'WS', is_ip):.1f}</td><td>N/A</td>
                    </tr>
                </table>

                <table>
                    <tr><th colspan="17" class="header-blue">Annual Cooling, Dehumidification, and Enthalpy Design Conditions</th></tr>
                    <tr class="gray-header">
                        <td rowspan="2">Hottest<br>Month</td><td rowspan="2">Hottest<br>Month<br>DB Range</td>
                        <td colspan="4">Cooling DB / MCWB ({h_T})</td>
                        <td colspan="4">Evaporation WB / MCDB ({h_T})</td>
                        <td colspan="3">Dehumid. DP/MCDB ({h_T}) and HR ({h_HR})</td>
                        <td colspan="3">Enthalpy / MCDB ({h_E} / {h_T})</td>
                        <td rowspan="2">Ext.<br>Max WB<br>({h_T})</td>
                    </tr>
                    <tr class="gray-header">
                        <td colspan="2">0.4%</td><td colspan="2">2%</td>
                        <td colspan="2">0.4%</td><td colspan="2">2%</td>
                        <td>0.4% DP</td><td>HR</td><td>MCDB</td>
                        <td>0.4% Enth</td><td>1% Enth</td><td>MCDB</td>
                    </tr>
                    <tr>
                        <td style="font-weight:bold;">{hottest_month}</td>
                        <td>{apply_u(df[df['Month'] == hottest_month]['DB'].max() - df[df['Month'] == hottest_month]['DB'].min(), 'TR', is_ip):.1f}</td>
                        <td>{apply_u(df['DB'].quantile(0.996), 'T', is_ip):.1f}</td><td>{apply_u(mc(df, 'DB', 'WB', df['DB'].quantile(0.996)), 'T', is_ip):.1f}</td>
                        <td>{apply_u(df['DB'].quantile(0.980), 'T', is_ip):.1f}</td><td>{apply_u(mc(df, 'DB', 'WB', df['DB'].quantile(0.980)), 'T', is_ip):.1f}</td>
                        <td>{apply_u(df['WB'].quantile(0.996), 'T', is_ip):.1f}</td><td>{apply_u(mc(df, 'WB', 'DB', df['WB'].quantile(0.996)), 'T', is_ip):.1f}</td>
                        <td>{apply_u(df['WB'].quantile(0.980), 'T', is_ip):.1f}</td><td>{apply_u(mc(df, 'WB', 'DB', df['WB'].quantile(0.980)), 'T', is_ip):.1f}</td>
                        <td>{apply_u(df['DP'].quantile(0.996), 'T', is_ip):.1f}</td><td>{apply_u(mc(df, 'DP', 'HR', df['DP'].quantile(0.996)), 'HR', is_ip):.1f}</td><td>{apply_u(mc(df, 'DP', 'DB', df['DP'].quantile(0.996)), 'T', is_ip):.1f}</td>
                        <td>{apply_u(df['Enth'].quantile(0.996), 'E', is_ip):.1f}</td><td>{apply_u(df['Enth'].quantile(0.990), 'E', is_ip):.1f}</td><td>{apply_u(mc(df, 'Enth', 'DB', df['Enth'].quantile(0.996)), 'T', is_ip):.1f}</td>
                        <td>{apply_u(df['WB'].max(), 'T', is_ip):.1f}</td>
                    </tr>
                </table>

                <table>
                    <tr><th colspan="12" class="header-blue">Extreme Annual Design Conditions</th></tr>
                    <tr class="gray-header">
                        <td colspan="3">Extreme Annual WS ({h_WS})</td><td colspan="4">Extreme Annual Temperature ({h_T})</td>
                        <td colspan="4">n-Year Return Period Values of Extreme Temperature ({h_T})</td>
                    </tr>
                    <tr class="gray-header">
                        <td>1%</td><td>2.5%</td><td>5%</td>
                        <td>DB Mean Min/Max</td><td>Standard dev</td><td>WB Mean Min/Max</td><td>Standard dev</td>
                        <td>n=5 years</td><td>n=10 years</td><td>n=20 years</td><td>n=50 years</td>
                    </tr>
                    <tr>
                        <td>{apply_u(df['WS'].quantile(0.990), 'WS', is_ip):.1f}</td><td>{apply_u(df['WS'].quantile(0.975), 'WS', is_ip):.1f}</td><td>{apply_u(df['WS'].quantile(0.950), 'WS', is_ip):.1f}</td>
                        <td>{apply_u(df['DB'].min(), 'T', is_ip):.1f} / {apply_u(df['DB'].max(), 'T', is_ip):.1f}</td><td>{apply_u(df['DB'].std(), 'TR', is_ip):.1f}</td>
                        <td>{apply_u(df['WB'].min(), 'T', is_ip):.1f} / {apply_u(df['WB'].max(), 'T', is_ip):.1f}</td><td>{apply_u(df['WB'].std(), 'TR', is_ip):.1f}</td>
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
            
            st.success("Reporte generado y estructurado exitosamente.")
            
            with st.expander("Resultados del Reporte de Diseño", expanded=True):
                components.html(html_preview_final, height=700, scrolling=True)
            
            safe_city = re.sub(r"[^A-Za-z0-9_-]+", "_", selected_city).strip("_")
            pdf_file = HTML(string=html_pdf_final).write_pdf()
            st.download_button(label="Descargar Reporte en PDF", data=pdf_file, file_name=f"Condiciones_Climaticas_EPW_{unit_suffix}_{safe_city}.pdf", mime="application/pdf")
