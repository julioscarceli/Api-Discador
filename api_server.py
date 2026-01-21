import os
import json
import redis
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# --- IMPORTAÇÕES DO BACKEND ---
from utils.mailing_api import get_active_campaign_metrics, api_import_mailling_upload, api_create_campaign
from scripts.cost_monitor import processar_dados_para_dashboard_formatado
from config.settings import ID_CAMPANHA_MG, ID_CAMPANHA_SP

try:
    from utils.login_manager import LoginManager
    login_manager = LoginManager()
except ImportError:
    login_manager = None

try:
    from scripts.restart_campaign import finalize_campaign_only
except ImportError:
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from scripts.restart_campaign import finalize_campaign_only

# --- INICIALIZAÇÃO ---
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

LOG_WORKER_URL = "https://api-discador-production-36c2.up.railway.app/api/logs/import"

async def report_to_monitor(region: str, action: str, status: str, message: str, file_name: str = "N/A"):
    try:
        payload = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "region": region, "action": action, "status": status, "message": message, "file_name": file_name
        }
        async with httpx.AsyncClient() as client:
            await client.post(LOG_WORKER_URL, json=payload, timeout=5.0)
    except Exception as e:
        print(f"Erro ao reportar log: {e}")

# --- ROTAS DE CUSTOS ---

@app.post("/api/atualizar-custos")
async def atualizar_custos(data: Dict[str, Any]):
    """Recebe do worker e salva na chave financeiro_custos."""
    try:
        r.set("financeiro_custos", json.dumps(data))
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/custos/")
async def get_custos_financeiros():
    """Recupera e formata para o Dashboard Lovable."""
    cache = r.get("financeiro_custos")
    if not cache:
        return {
            "saldo_atual": "R$ 0,00",
            "custo_diario": "R$ 0,00",
            "custo_semanal": "R$ 0,00"
        }
    return processar_dados_para_dashboard_formatado(json.loads(cache))

# --- MONITORAMENTO E OPERAÇÕES ---

@app.get("/api/status/{server_id}")
async def get_status_metrics(server_id: str):
    return await get_active_campaign_metrics(server_id.upper())

@app.post("/api/upload/{server_id}")
async def upload_mailing(server_id: str, data: Dict[str, Any]):
    try:
        srv = server_id.upper()
        mailling_name = data.get('mailling_name', f"Upload_{srv}")
        id_oficial = ID_CAMPANHA_SP if srv == "SP" else ID_CAMPANHA_MG
        
        # 1. Limpeza UI
        await report_to_monitor(srv, "Limpeza UI", "processando", "Limpando campanha ativa", mailling_name)
        await finalize_campaign_only(server=srv)

        # 2. Sessão e Campanha
        session_cookies = await login_manager.get_active_session(srv) if login_manager else {}
        id_dinamico = await api_create_campaign(server=srv, mailing_name=mailling_name, cookies=session_cookies)
        id_final = str(id_dinamico if id_dinamico else id_oficial)

        # 3. Importação
        resultado = await api_import_mailling_upload(
            server=srv, campaign_id=id_final, file_content_base64=data.get('file_content_base64'),
            mailling_name=mailling_name, login_crm=data.get('login_crm', 'DASHBOARD_LOVABLE')
        )
        return {"status": "sucesso", "campanha_id": id_final, "resposta": resultado}
    except Exception as e:
        await report_to_monitor(server_id.upper(), "Erro Fatal", "erro", str(e), data.get('mailling_name', 'N/A'))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs/")
async def get_logs():
    return [{"timestamp": datetime.now().strftime('%H:%M:%S'), "acao": "Sincronização", "regiao": "REDIS-SERVER", "status": "Ativo"}]













