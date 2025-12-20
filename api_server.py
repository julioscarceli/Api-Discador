import os
import json
import redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# --- IMPORTAÇÕES DO BACKEND ---
from utils.mailing_api import get_active_campaign_metrics, api_import_mailling_upload
from scripts.cost_monitor import processar_dados_para_dashboard_formatado
# --- FIM IMPORTAÇÕES ---

app = FastAPI(title="Dialing Hub API Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REDIS CONFIG ---
REDIS_URL = os.getenv("REDIS_URL", "redis://default:BMetYritSRFXIbozyBtCQpJpQKOxnnZE@redis.railway.internal:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

def get_estado_redis():
    estado = r.get("estado_financeiro")
    if estado:
        return json.loads(estado)
    return {
        "total_acumulado_semana": 0.0,
        "ultimo_custo_diario_recebido": 0.0,
        "dia_da_ultima_coleta": -1, # 0=Segunda
        "ultima_data_reset": ""
    }

@app.post("/api/atualizar-custos")
async def atualizar_custos(data: Dict[str, Any]):
    try:
        estado = get_estado_redis()
        custo_hoje = data.get("custo_diario_total", 0.0)
        hoje = datetime.now()
        dia_semana = hoje.weekday() 
        
        print(f"\n[API-REDIS] 📥 Recebido: R$ {custo_hoje:.2f}")

        # 1. RESET SEMANAL (SEGUNDA-FEIRA)
        if dia_semana == 0 and estado["dia_da_ultima_coleta"] != 0:
            print("[API-LOG] 🗓️ Segunda-feira detectada. Resetando acumulado semanal.")
            estado["total_acumulado_semana"] = 0.0

        # 2. VIRADA DE DIA (ACUMULAÇÃO)
        if custo_hoje < estado["ultimo_custo_diario_recebido"]:
            valor_ontem = estado["ultimo_custo_diario_recebido"]
            estado["total_acumulado_semana"] += valor_ontem
            print(f"[API-LOG] 💰 Virada de dia! Somado R$ {valor_ontem:.2f} ao acumulado Redis.")

        # 3. PERSISTÊNCIA
        estado["ultimo_custo_diario_recebido"] = custo_hoje
        estado["dia_da_ultima_coleta"] = dia_semana
        r.set("estado_financeiro", json.dumps(estado))
        
        # Calcula total e salva cache para Lovable
        total_semanal = estado["total_acumulado_semana"] + custo_hoje
        data["custo_semanal_acumulado"] = total_semanal
        r.set("cache_lovable", json.dumps(data))

        print(f"[API-SUCCESS] ✅ Redis Atualizado. Semanal: R$ {total_semanal:.2f}")
        return {"status": "sucesso"}
    except Exception as e:
        print(f"[API-ERROR] ❌ Erro Redis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/custos/")
async def get_custos_financeiros():
    cache = r.get("cache_lovable")
    if not cache:
        return {"saldo_atual": "Aguardando...", "custo_diario": "0,00", "custo_semanal": "0,00"}
    return processar_dados_para_dashboard_formatado(json.loads(cache))

@app.get("/api/status/{server_id}")
async def get_status_metrics(server_id: str):
    return await get_active_campaign_metrics(server_id.upper())

@app.post("/api/upload/{server_id}")
async def upload_mailing(server_id: str, data: Dict[str, Any]):
    return await api_import_mailling_upload(
        server=server_id.upper(),
        campaign_id=data['campaign_id'],
        file_content_base64=data['file_content_base64'],
        mailling_name=data['mailling_name'],
        login_crm=data.get('login_crm', 'DASHBOARD_LOVABLE')
    )

@app.get("/api/logs/")
async def get_logs():
    return [{"timestamp": datetime.now().strftime('%H:%M:%S'), "acao": "Sincronização", "regiao": "REDIS-SERVER", "status": "Ativo"}]





