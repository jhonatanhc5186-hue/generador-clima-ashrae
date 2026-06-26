import os
import requests
from fastapi import FastAPI, Request
from supabase import create_client

app = FastAPI()

# 1. Credenciales (Se leerán desde el servidor por seguridad)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY") # AQUÍ SÍ USAMOS LA SECRET KEY
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN") # Tu token de Mercado Pago

supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

@app.get("/")
def home():
    return {"mensaje": "Servidor Webhook Activo"}

@app.post("/webhook")
async def mercado_pago_webhook(request: Request):
    try:
        # 1. Recibir el "aviso" de Mercado Pago
        payload = await request.json()
        
        # 2. Confirmar que es un evento de pago
        if payload.get("type") == "payment":
            payment_id = payload.get("data", {}).get("id")
            
            # 3. Consultar a Mercado Pago para evitar fraudes
            headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
            mp_response = requests.get(f"https://api.mercadopago.com/v1/payments/{payment_id}", headers=headers)
            
            if mp_response.status_code == 200:
                payment_data = mp_response.json()
                status = payment_data.get("status")
                email = payment_data.get("payer", {}).get("email")
                
                # 4. Escribir en tu base de datos Supabase si fue aprobado
                if status == "approved" and email:
                    supabase.table("pagos").upsert({
                        "external_reference": str(payment_id),
                        "email": email,
                        "status": status
                    }, on_conflict="external_reference").execute()
                    
        return {"status": "recibido"}
    except Exception as e:
        print(f"Error interno: {e}")
        return {"status": "error"}
