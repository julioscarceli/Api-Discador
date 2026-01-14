import os
import json
import redis
import httpx  # Necessário para enviar logs ao import-monitor
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# --- IMPORTAÇÕES DO BACKEND ---
from utils.mailing_api import get_active_campaign_metrics, api_import_mailling_upload
from scripts.cost_monitor import processar_dados_para_dashboard_formatado
from config.settings import ID_CAMPANHA_MG, ID_CAMPANHA_SP

# 🚨 AJUSTE DE IMPORTAÇÃO (Item 3): Nome corrigido de 'restarter_campaign' para 'restart_campaign'
try:
    from scripts.restart_campaign import finalize_campaign_only
except ImportError:
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from scripts.restart_campaign import finalize_campaign_only
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

# URL do seu worker de monitoramento dedicado no Railway
LOG_WORKER_URL = "https://api-discador-production-36c2.up.railway.app/api/logs/import"

async def report_to_monitor(region: str, action: str, status: str, message: str, file_name: str = "N/A"):
    """Envia logs para o worker de import-monitor para acompanhamento em tempo real"""
    payload = {
        "region": region,
        "action": action,
        "status": status,
        "message": message,
        "file_name": file_name,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }
    try:
        async with httpx.AsyncClient() as client:
            await client.post(LOG_WORKER_URL, json=payload, timeout=5.0)
    except Exception as e:
        print(f"Erro ao reportar log ao monitor: {e}")

def get_estado_redis():
    estado = r.get("estado_financeiro")
    if estado:
        return json.loads(estado)
    return {
        "total_acumulado_semana": 0.0,
        "ultimo_custo_diario_recebido": 0.0,
        "dia_da_ultima_coleta": -1, 
        "ultima_data_reset": ""
    }

@app.post("/api/atualizar-custos")
async def atualizar_custos(data: Dict[str, Any]):
    try:
        estado = get_estado_redis()
        custo_hoje = data.get("custo_diario_total", 0.0)
        hoje = datetime.now()
        dia_semana = hoje.weekday() 
        
        print(f"\n[API-REDIS] 📥 Recebido do Worker: R$ {custo_hoje:.2f}")

        if dia_semana == 0:
            if estado["total_acumulado_semana"] != 0.0:
                print("[API-LOG] 🗓️ É SEGUNDA-FEIRA! Zerando resíduos da semana passada.")
                estado["total_acumulado_semana"] = 0.0
            total_semanal = custo_hoje 
        else:
            if custo_hoje < estado["ultimo_custo_diario_recebido"]:
                estado["total_acumulado_semana"] += estado["ultimo_custo_diario_recebido"]
                print(f"[API-LOG] 💰 Virada de dia detectada! Acumulado: R$ {estado['total_acumulado_semana']:.2f}")
            total_semanal = estado["total_acumulado_semana"] + custo_hoje

        estado["ultimo_custo_diario_recebido"] = custo_hoje
        estado["dia_da_ultima_coleta"] = dia_semana
        r.set("estado_financeiro", json.dumps(estado))
        
        data["custo_semanal_acumulado"] = total_semanal
        r.set("cache_lovable", json.dumps(data))

        print(f"[API-SUCCESS] ✅ Redis Atualizado. Hoje: R$ {custo_hoje:.2f} | Semanal: R$ {total_semanal:.2f}")
        return {"status": "sucesso"}
        
    except Exception as e:
        print(f"[API-ERROR] ❌ Erro no processamento: {e}")
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
    try:
        srv = server_id.upper()
        mailling_name = data.get('mailling_name', f"Upload_{srv}")
        
        if srv == "SP":
            id_oficial = ID_CAMPANHA_SP 
        elif srv == "MG":
            id_oficial = ID_CAMPANHA_MG 
        else:
            raise HTTPException(status_code=400, detail="Servidor inválido. Use MG ou SP.")

        print(f"[API-UPLOAD] 📥 Recebido mailing para {srv} (ID: {id_oficial})")

        # ============================================================
        # 🧹 PASSO 1: LIMPEZA PREVENTIVA (ITEM 3)
        # ============================================================
        await report_to_monitor(srv, "Limpeza UI", "processando", "Finalizando campanha antiga via UI antes do upload", mailling_name)
        
        # Chama a função do script restart_campaign.py para limpar a tela do discador
        limpeza_sucesso = await finalize_campaign_only(server=srv)
        
        if limpeza_sucesso:
            await report_to_monitor(srv, "Limpeza UI", "sucesso", "Campanha antiga finalizada com sucesso", mailling_name)
        else:
            await report_to_monitor(srv, "Limpeza UI", "erro", "Não foi possível finalizar campanha via UI", mailling_name)

        # ============================================================
        # 🚀 PASSO 2: UPLOAD DO NOVO MAILING (ITEM 4)
        # ============================================================
        resultado = await api_import_mailling_upload(
            server=srv,
            campaign_id=str(id_oficial),
            file_content_base64=data.get('file_content_base64'),
            mailling_name=mailling_name,
            login_crm=data.get('login_crm', 'DASHBOARD_LOVABLE')
        )

        return {
            "status": "sucesso",
            "servidor": srv,
            "campanha_id": id_oficial,
            "resposta_discador": resultado
        }

    except Exception as e:
        print(f"[API-ERROR] ❌ Erro no upload: {str(e)}")
        await report_to_monitor(server_id.upper(), "Erro Fatal", "erro", str(e), data.get('mailling_name', 'N/A'))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs/")
async def get_logs():
    return [{"timestamp": datetime.now().strftime('%H:%M:%S'), "acao": "Sincronização", "regiao": "REDIS-SERVER", "status": "Ativo"}]











