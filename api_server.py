# api_server.py (VERSÃO COM CACHE EM MEMÓRIA PARA RECEBER DADOS DO WORKER)

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
from dotenv import load_dotenv
from datetime import datetime

# Carrega variáveis de ambiente
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

# 🚨 VARIÁVEL GLOBAL: Guarda os últimos dados financeiros na RAM
cache_financeiro_memoria = {}

# ====================================================================
# ENDPOINT NOVO: RECEBER DADOS DO WORKER (POST /api/atualizar-custos)
# ====================================================================
@app.post("/api/atualizar-custos")
async def atualizar_custos(data: Dict[str, Any]):
    """Recebe dados brutos do cost-monitor.py e guarda no cache de memória."""
    global cache_financeiro_memoria
    cache_financeiro_memoria = data
    print(f"--- [{datetime.now().strftime('%H:%M:%S')}] ✅ Cache atualizado via Worker ---")
    return {"status": "sucesso", "timestamp": datetime.now().isoformat()}

# ====================================================================
# ENDPOINT 2: CUSTOS FINANCEIROS (GET /api/custos/)
# ====================================================================
@app.get("/api/custos/")
async def get_custos_financeiros():
    """Retorna os dados guardados em memória. Se vazio, tenta ler o ficheiro local por segurança."""
    global cache_financeiro_memoria

    if not cache_financeiro_memoria:
        # Se o worker ainda não enviou nada via POST, a API tenta uma falha silenciosa amigável
        return {
            "saldo_atual": "Carregando...",
            "custo_diario": "Carregando...",
            "custo_semanal": "Carregando...",
            "data_coleta": datetime.now().isoformat()
        }

    # Formata os dados para o padrão do dashboard
    return processar_dados_para_dashboard_formatado(cache_financeiro_memoria)

# ====================================================================
# OUTROS ENDPOINTS (MANTIDOS)
# ====================================================================
@app.get("/api/status/{server_id}")
async def get_status_metrics(server_id: str):
    try:
        data = await get_active_campaign_metrics(server_id.upper())
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload/{server_id}")
async def upload_mailing(server_id: str, data: Dict[str, Any]):
    upload_result = await api_import_mailling_upload(
        server=server_id.upper(),
        campaign_id=data['campaign_id'],
        file_content_base64=data['file_content_base64'],
        mailling_name=data['mailling_name'],
        login_crm=data.get('login_crm', 'DASHBOARD_MANUAL')
    )
    return upload_result

@app.get("/api/logs/")
async def get_logs():
    return [{"timestamp": datetime.now().strftime('%H:%M:%S'), "acao": "Sincronização", "regiao": "SISTEMA", "status": "Sucesso", "registros": 0}]
