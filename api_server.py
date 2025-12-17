# api_server.py (VERSÃO FINAL E ESTÁVEL)

import os
import asyncio
import sys
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
from dotenv import load_dotenv
from datetime import datetime

# Carrega variáveis de ambiente
load_dotenv()

# --- IMPORTAÇÕES DO BACKEND ---
from utils.mailing_api import get_active_campaign_metrics, api_import_mailling_upload
# 🚨 IMPORTAÇÃO APENAS das funções de CACHE e FORMATAÇÃO
from scripts.cost_monitor import ler_cache_custos, processar_dados_para_dashboard_formatado
# --- FIM IMPORTAÇÕES ---

app = FastAPI(title="Dialing Hub API Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ====================================================================
# ENDPOINT 1: STATUS DO DISCADOR (GET /api/status/{server_id})
# ====================================================================
@app.get("/api/status/{server_id}")
async def get_status_metrics(server_id: str):
    """Busca Nome, Progresso e Saídas ativas para um servidor (MG ou SP)."""
    try:
        data = await get_active_campaign_metrics(server_id.upper())

        if data.get('nome') == "ERRO API":
            return data

        return data

    except Exception as e:
        print(f"Erro inesperado no endpoint /status/{server_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno no servidor: {str(e)}")


# ====================================================================
# ENDPOINT 2: CUSTOS FINANCEIROS (GET /api/custos/)
# ====================================================================
@app.get("/api/custos/")
async def get_custos_financeiros():
    """Busca dados de custos do arquivo de cache. O scraping é feito por um worker externo."""

    print(f"--- [{datetime.now().strftime('%H:%M:%S')}] Lendo Cache de Custos ---")

    # 🚨 CRÍTICO: Apenas lê o arquivo de cache
    dados_brutos = ler_cache_custos()

    if "erro" in dados_brutos:
        detail = dados_brutos.get('erro', 'Cache indisponível.')
        # Retorna 503 se o cache falhar ou não existir
        raise HTTPException(status_code=503, detail=f"Falha ao obter dados de custos: {detail}")

    # Formata os dados lidos do cache e retorna
    return processar_dados_para_dashboard_formatado(dados_brutos)


# ====================================================================
# ENDPOINT 3: UPLOAD MANUAL DE MAILING (POST /api/upload/{server_id})
# ====================================================================
@app.post("/api/upload/{server_id}")
async def upload_mailing(server_id: str, data: Dict[str, Any]):
    """Dispara o Worker de Importação e Upload via API."""
    server = server_id.upper()

    required_keys = ["file_content_base64", "campaign_id", "mailling_name"]
    if not all(key in data for key in required_keys):
        raise HTTPException(status_code=400, detail="Dados de upload incompletos.")

    upload_result = await api_import_mailling_upload(
        server=server,
        campaign_id=data['campaign_id'],
        file_content_base64=data['file_content_base64'],
        mailling_name=data['mailling_name'],
        login_crm=data.get('login_crm', 'DASHBOARD_MANUAL')
    )

    if not upload_result.get('success'):
        detail = upload_result.get('erro') or upload_result.get('mensagem') or "Falha desconhecida no upload."
        raise HTTPException(status_code=500, detail=f"Falha na Importação: {detail}")

    return upload_result


# ====================================================================
# ENDPOINT 4: HISTÓRICO DE LOGS (GET /api/logs/)
# ====================================================================
@app.get("/api/logs/")
async def get_logs():
    """Busca o histórico de importações para a tabela de logs."""
    return [
        {"timestamp": datetime.now().strftime('%H:%M:%S'), "acao": "Consulta Financeira", "regiao": "SISTEMA", "status": "Sucesso", "registros": 0},
    ]