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

# ====================================================================
# 🧠 MEMÓRIA DA CALCULADORA (Persiste enquanto o card estiver Online)
# ====================================================================
estado_financeiro = {
    "total_acumulado_semana": 0.0,
    "ultimo_custo_diario_recebido": 0.0,
    "dia_da_ultima_coleta": -1,  # 0=Segunda, 6=Domingo
    "cache_completo": {}
}

# ====================================================================
# ENDPOINT: RECEBER DADOS DO WORKER (POST /api/atualizar-custos)
# ====================================================================
@app.post("/api/atualizar-custos")
async def atualizar_custos(data: Dict[str, Any]):
    global estado_financeiro
    
    custo_hoje = data.get("custo_diario_total", 0.0)
    hoje_data = datetime.now()
    dia_semana_hoje = hoje_data.weekday()

    print(f"--- [{hoje_data.strftime('%H:%M:%S')}] Processando Atualização ---")

    # 1. LÓGICA DE RESET SEMANAL (Se for segunda-feira e a última vez foi outro dia)
    if dia_semana_hoje == 0 and estado_financeiro["dia_da_ultima_coleta"] != 0:
        print("🗓️ Nova semana detectada! Resetando total acumulado.")
        estado_financeiro["total_acumulado_semana"] = 0.0

    # 2. LÓGICA DE ACUMULAÇÃO DIÁRIA
    # Se o valor recebido agora é menor que o último, o discador resetou (virou o dia)
    if custo_hoje < estado_financeiro["ultimo_custo_diario_recebido"]:
        # Somamos o valor máximo alcançado ontem ao total da semana
        estado_financeiro["total_acumulado_semana"] += estado_financeiro["ultimo_custo_diario_recebido"]
        print(f"💰 Dia virou! R$ {estado_financeiro['ultimo_custo_diario_recebido']} somado ao acumulado semanal.")

    # 3. ATUALIZAÇÃO DO ESTADO
    estado_financeiro["ultimo_custo_diario_recebido"] = custo_hoje
    estado_financeiro["dia_da_ultima_coleta"] = dia_semana_hoje
    
    # Injetamos o cálculo final no JSON que vai para a Lovable
    data["custo_semanal_acumulado"] = estado_financeiro["total_acumulado_semana"] + custo_hoje
    estado_financeiro["cache_completo"] = data

    print(f"✅ Dashboard atualizado. Semanal: R$ {data['custo_semanal_acumulado']:.2f}")
    return {"status": "sucesso"}

# ====================================================================
# ENDPOINT: CONSULTA DA LOVABLE (GET /api/custos/)
# ====================================================================
@app.get("/api/custos/")
async def get_custos_financeiros():
    global estado_financeiro

    if not estado_financeiro["cache_completo"]:
        return {
            "saldo_atual": "Carregando...",
            "custo_diario": "Carregando...",
            "custo_semanal": "Carregando...",
            "data_coleta": datetime.now().isoformat()
        }

    return processar_dados_para_dashboard_formatado(estado_financeiro["cache_completo"])


# ====================================================================
# ENDPOINTS OPERACIONAIS (Status e Upload)
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


