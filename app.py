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

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Condiciones Climáticas de Diseño", layout="wide", initial_sidebar_state="collapsed")

# Carga de credenciales desde variables de entorno de Render
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Validación de seguridad
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Error: Las variables de entorno SUPABASE_URL o SUPABASE_KEY no están configuradas.")
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Función de verificación robusta
def verificar_pago_en_db(email):
    try:
        # Normalizamos a minúsculas y quitamos espacios
        email_limpio = email.strip().lower()
        # Consulta
        result = supabase.table("pagos").select("*").eq("email", email_limpio).eq("status", "approved").execute()
        return len(result.data) > 0
    except Exception as e:
        st.error(f"Error al conectar con la base de datos: {e}")
        return False

# --- ESTADOS DE SESIÓN ---
if 'lat' not in st.session_state: st.session_state.lat = -16.3410
if 'lon' not in st.session_state: st.session_state.lon = -71.5830
if 'pagado' not in st.session_state: st.session_state.pagado = False

# --- 2. CALLBACK DE BÚSQUEDA GEOGRÁFICA ---
def execute_search():
    st.session_state.pop('search_success', None)
    st.session_state.pop('search_error', None)
    query = st.session_state.get('search_input', '')
    if query:
        safe_query = urllib.parse.quote(query.strip())
        headers = {'User-Agent': 'Mozilla/5.0'}
        encontrado = False
        try:
            url = f"https://nominatim.openstreetmap.org/search?q={safe_query}&format=json&limit=1"
            res = requests.get(url, headers=headers, timeout=5).json()
            if res:
                st.session_state.lat = float(res[0]['lat'])
                st.session_state.lon = float(res[0]['lon'])
                st.session_state.search_success = f"📍 Ubicación: {res[0]['display_name']}"
                encontrado = True
        except: pass
        if not encontrado: st.session_state.search_error = "No se encontró la ubicación."

# --- 3. FUNCIONES TERMODINÁMICAS Y AUXILIARES ---
def calc_wb(T, RH):
    return T * np.arctan(0.151977 * (RH + 8.313659)**0.5) + np.arctan(T + RH) - np.arctan(RH - 1.676331) + 0.00391838 * (RH)**1.5 * np.arctan(0.023101 * RH) - 4.686035

def calc_enthalpy(T, HR):
    return 1.006 * T + (HR/1000) * (2501 + 1.86 * T)

def mc(sub, base_col, target_col, t):
    h = sub[(sub[base_col] >= t - 0.2) & (sub[base_col] <= t + 0.2)]
    return h[target_col].mean() if not h.empty else sub[target_col].mean()

def fmt_u(v, decimals=1):
    if pd.isna(v) or v in ('N/A', '', None): return 'N/A'
    try: return f"{float(v):.{decimals}f}" if not np.isinf(float(v)) else 'N/A'
    except: return str(v)

def clean_city_name(filename):
    return filename.replace(".epw", "")

def get_epw_mapping():
    if not os.path.exists("data"): return {}
    return {clean_city_name(f): f for f in sorted([f for f in os.listdir("data") if f.endswith(".epw")])}

def format_coord(val, is_lat):
    try: return f"{abs(float(val)):.4f}{'N' if float(val) >= 0 else 'S'}" if is_lat else f"{abs(float(val)):.4f}{'E' if float(val) >= 0 else 'W'}"
    except: return str(val)

# --- 4. INTERFAZ ---
st.markdown("<h2 style='text-align: center; color: #1f456e;'>CONDICIONES CLIMÁTICAS DE DISEÑO</h2>", unsafe_allow_html=True)
col_params, col_map = st.columns([1, 2.5], gap="large")

with col_params:
    modo = st.radio("Fuente de Datos:", ["Coordenadas Satelitales (NASA)", "Estación Local (Datos EPW)"])
    
    # Lógica de inputs simplificada para este ejemplo integral
    if "Satelitales" in modo:
        lat = st.number_input("Latitud", format="%.4f", key="lat")
        lon = st.number_input("Longitud", format="%.4f", key="lon")
        usar_local = False
    else:
        usar_local = True
        st.warning("Selecciona estación local (asegúrate de tener la carpeta 'data' subida).")

    st.markdown("---")
    
    # CONTROL DE ACCESO
    if not st.session_state.pagado:
        st.info("🔒 Ingrese el correo registrado en Mercado Pago para activar el acceso.")
        email_usuario = st.text_input("Correo electrónico:")
        if st.button("Validar Acceso"):
            if verificar_pago_en_db(email_usuario):
                st.session_state.pagado = True
                st.rerun()
            else:
                st.error("No se encontró un pago aprobado para este correo.")
        st.markdown(f"[💳 Ir a Pagar (S/ 2.00)](https://mpago.la/1bhrXb7)", unsafe_allow_html=True)
    else:
        st.success("✅ Acceso concedido.")
        btn_generar = st.button("Generar Reporte Maestro", type="primary")

# --- 5. LÓGICA DE GENERACIÓN ---
if 'btn_generar' in locals() and btn_generar:
    st.write("Generando reporte...")
    # (Aquí va toda tu lógica de requests NASA o procesamiento EPW que tenías originalmente)
