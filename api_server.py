import os
import json
import redis
import httpx
import asyncio
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

# Tenta importar o LoginManager para capturar PHPSESSID
try:
    from utils.login_manager import LoginManager
    login_manager = LoginManager()
except ImportError:
    login_manager = None

# Tenta importar a função de finalização (limpeza de UI)
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

# URL para logs externos (Dashboard/Monitor)
LOG_WORKER_URL = "https://api-discador-production-36c2.up.railway.app/api/logs/import"

async def report_to_monitor(region: str, action: str, status: str, message: str, file_name: str = "N/A"):
    """Envia o status da operação para o sistema de monitoramento de logs."""
    log_data = {
        "region": region,
        "action": action,
        "status": status,
        "message": message,
        "file_name": file_name,
        "timestamp": datetime.now().isoformat()
    }
    print(f"[{region}] {action}: {message}")
    try:
        async with httpx.AsyncClient() as client:
            await client.post(LOG_WORKER_URL, json=log_data, timeout=5.0)
    except Exception as e:
        print(f"Erro ao reportar log: {e}")

# --- ROTAS DE CUSTOS ---

@app.post("/api/atualizar-custos")
async def atualizar_custos(data: Dict[str, Any]):
    """Recebe dados do cost_monitor.py e armazena no Redis."""
    try:
        r.set("financeiro_dashboard", json.dumps(data))
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/custos/")
async def get_custos_financeiros():
    """Retorna os custos formatados para o Dashboard."""
    cache = r.get("financeiro_dashboard")
    if not cache:
        return {
            "saldo_atual": "R$ 0,00",
            "custo_diario": "R$ 0,00",
            "custo_semanal": "R$ 0,00",
            "data_coleta": datetime.now().isoformat()
        }
    return processar_dados_para_dashboard_formatado(json.loads(cache))

# --- MONITORAMENTO E OPERAÇÕES ---

@app.get("/api/status/{server_id}")
async def get_status_metrics(server_id: str):
    """Consulta métricas em tempo real (mailing, progresso, canais)."""
    return await get_active_campaign_metrics(server_id.upper())

@app.post("/api/upload/{server_id}")
async def upload_mailing(server_id: str, data: Dict[str, Any]):
    """
    Fluxo principal de Importação:
    1. Limpa campanha ativa (UI).
    2. Captura PHPSESSID.
    3. Cria/Associa campanha via API.
    4. Faz o upload do Mailing.
    """
    srv = server_id.upper()
    mailling_name = data.get('mailling_name', f"Upload_{srv}")
    id_oficial = ID_CAMPANHA_SP if srv == "SP" else ID_CAMPANHA_MG
    
    try:
        # 1. Limpeza UI (Chama Playwright para finalizar mailing atual)
        await report_to_monitor(srv, "Limpeza UI", "processando", "Limpando campanha ativa", mailling_name)
        await finalize_campaign_only(server=srv)

        # 2. Sessão e Campanha
        # Captura PHPSESSID para garantir que a API de importação funcione
        session_cookies = await login_manager.get_active_session(srv) if login_manager else {}
        
        # Cria ou obtém o ID da campanha dinâmica
        id_dinamico = await api_create_campaign(server=srv, mailing_name=mailling_name, cookies=session_cookies)
        id_final = str(id_dinamico if id_dinamico else id_oficial)

        # 3. Importação via POST API
        resultado = await api_import_mailling_upload(
            server=srv, 
            campaign_id=id_final, 
            file_content_base64=data.get('file_content_base64'),
            mailling_name=mailling_name, 
            login_crm=data.get('login_crm', 'DASHBOARD_LOVABLE')
        )
        
        await report_to_monitor(srv, "IMPORTAÇÃO CONCLUÍDA", "sucesso", f"Arquivo aceito e processado. ID: {id_final}", mailling_name)
        return {"status": "sucesso", "campanha_id": id_final, "resposta": resultado}

    except Exception as e:
        msg_erro = str(e)
        print(f"[{srv}] ❌ Erro Fatal no Processamento: {msg_erro}")
        await report_to_monitor(srv, "Erro Fatal", "erro", msg_erro, mailling_name)
        raise HTTPException(status_code=500, detail=msg_erro)

@app.get("/api/logs/")
async def get_logs():
    """Rota de fallback para listar logs de atividade."""
    return [{
        "timestamp": datetime.now().strftime('%H:%M:%S'), 
        "acao": "Sincronização", 
        "regiao": "GATEWAY", 
        "status": "Online"
    }]


@app.post("/api/worker/logs")
async def receber_logs_worker(data: Dict[str, Any]):
    msg = data.get("message", "")
    # Em vez de printar aqui, enviamos para o canal 'logs_financeiro' no Redis
    r.publish("logs_financeiro", msg) 
    return {"status": "ok"}



if __name__ == "__main__":
    import uvicorn
    # Porta 8080 padrão para Railway
    uvicorn.run(app, host="0.0.0.0", port=8080)

















