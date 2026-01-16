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
# Adicionado api_create_campaign na importação do mailing_api
from utils.mailing_api import get_active_campaign_metrics, api_import_mailling_upload, api_create_campaign
from scripts.cost_monitor import processar_dados_para_dashboard_formatado
from config.settings import ID_CAMPANHA_MG, ID_CAMPANHA_SP

# Importação do login_manager para suportar a criação de campanha com sessão
try:
    from utils.login_manager import LoginManager
    login_manager = LoginManager()
except ImportError:
    login_manager = None

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
    try:
        payload = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "region": region,
            "action": action,
            "status": status,
            "message": message,
            "file_name": file_name
        }
        async with httpx.AsyncClient() as client:
            await client.post(LOG_WORKER_URL, json=payload, timeout=5.0)
    except Exception as e:
        print(f"Erro ao reportar log ao monitor: {e}")

def get_estado_redis():
    # Mantido conforme original
    return {}

@app.post("/api/atualizar-custos")
async def atualizar_custos(data: Dict[str, Any]):
    try:
        r.set("financeiro_custos", json.dumps(data))
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/custos/")
async def get_custos_financeiros():
    cache = r.get("financeiro_custos")
    if not cache:
        return []
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

        print(f"[API-UPLOAD] 📥 Recebido mailing para {srv} (ID Padrão: {id_oficial})")

        # ============================================================
        # 🧹 PASSO 1: LIMPEZA PREVENTIVA (ITEM 3)
        # ============================================================
        await report_to_monitor(srv, "Limpeza UI", "processando", "Finalizando campanha antiga via UI antes do upload", mailling_name)
        
        limpeza_sucesso = await finalize_campaign_only(server=srv)
        
        if limpeza_sucesso:
            await report_to_monitor(srv, "Limpeza UI", "sucesso", "Campanha antiga finalizada com sucesso", mailling_name)
        else:
            await report_to_monitor(srv, "Limpeza UI", "erro", "Não foi possível finalizar campanha via UI", mailling_name)

        # ============================================================
        # 🚀 NOVO PASSO: CRIAÇÃO DA CAMPANHA E VÍNCULO DE ID
        # ============================================================
        # 1. Obter Sessão para criar campanha (Cookie)
        session_cookies = {}
        if login_manager:
            session_cookies = await login_manager.get_active_session(srv)

        # 2. Criar campanha e capturar o ID Dinâmico
        await report_to_monitor(srv, "Vínculo API", "processando", "Criando entidade de campanha para vincular", mailling_name)
        id_dinamico = await api_create_campaign(server=srv, mailing_name=mailling_name, cookies=session_cookies)

        # 3. Definir ID final (Dinamico se sucesso, Oficial se falha)
        id_final = str(id_dinamico if id_dinamico else id_oficial)
        print(f"[API-VINCULO] 🎯 Utilizando ID: {id_final} (Dinamico: {id_dinamico is not None})")

        # ============================================================
        # 🚀 PASSO 2: UPLOAD DO NOVO MAILING (ITEM 4)
        # ============================================================
        resultado = await api_import_mailling_upload(
            server=srv,
            campaign_id=id_final,
            file_content_base64=data.get('file_content_base64'),
            mailling_name=mailling_name,
            login_crm=data.get('login_crm', 'DASHBOARD_LOVABLE')
        )

        return {
            "status": "sucesso",
            "servidor": srv,
            "campanha_id": id_final,
            "id_gerado_api": id_dinamico,
            "resposta_discador": resultado
        }

    except Exception as e:
        print(f"[API-ERROR] ❌ Erro no upload: {str(e)}")
        await report_to_monitor(server_id.upper(), "Erro Fatal", "erro", str(e), data.get('mailling_name', 'N/A'))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs/")
async def get_logs():
    return [{"timestamp": datetime.now().strftime('%H:%M:%S'), "acao": "Sincronização", "regiao": "REDIS-SERVER", "status": "Ativo"}]












