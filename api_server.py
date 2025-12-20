import os
import json
import redis
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
# 🗄️ CONFIGURAÇÃO REDIS (Persistência Total)
# ====================================================================
# Use a variável de ambiente REDIS_URL no Railway ou o link direto
REDIS_URL = os.getenv("REDIS_URL", "redis://default:BMetYritSRFXIbozyBtCQpJpQKOxnnZE@redis.railway.internal:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

def get_estado():
    """Recupera o estado financeiro do Redis ou cria um novo se vazio."""
    estado = r.get("estado_financeiro")
    if estado:
        return json.loads(estado)
    return {
        "total_acumulado_semana": 0.0,
        "ultimo_custo_diario_recebido": 0.0,
        "dia_da_ultima_coleta": -1,  # 0=Segunda, 5=Sábado, 6=Domingo
        "ultima_data_reset": ""
    }

def salvar_estado(estado):
    """Salva o estado atualizado no Redis."""
    r.set("estado_financeiro", json.dumps(estado))

# ====================================================================
# ENDPOINT: RECEBER DADOS DO WORKER (POST /api/atualizar-custos)
# ====================================================================
@app.post("/api/atualizar-custos")
async def atualizar_custos(data: Dict[str, Any]):
    estado = get_estado()
    
    custo_hoje = data.get("custo_diario_total", 0.0)
    hoje_data = datetime.now()
    dia_semana_hoje = hoje_data.weekday() 
    hoje_str = hoje_data.strftime('%Y-%m-%d')

    print(f"--- [{hoje_data.strftime('%H:%M:%S')}] Processando Atualização via Redis ---")

    # 1. LÓGICA DE RESET SEMANAL (Segunda-feira é o dia 0)
    # Se hoje é segunda e o último registro não foi segunda, resetamos o balde semanal.
    if dia_semana_hoje == 0 and estado["dia_da_ultima_coleta"] != 0:
        print("🗓️ Início de semana (Segunda)! Resetando acumulado semanal.")
        estado["total_acumulado_semana"] = 0.0

    # 2. LÓGICA DE ACUMULAÇÃO (Virada de Dia)
    # Se o custo que chegou agora é menor que o último registrado, significa que o discador zerou (virou o dia)
    if custo_hoje < estado["ultimo_custo_diario_recebido"]:
        # Somamos o valor final do dia anterior ao acumulado da semana
        estado["total_acumulado_semana"] += estado["ultimo_custo_diario_recebido"]
        print(f"💰 Virada de dia detectada! R$ {estado['ultimo_custo_diario_recebido']:.2f} somados ao acumulado.")

    # 3. ATUALIZAÇÃO DO ESTADO NO REDIS
    estado["ultimo_custo_diario_recebido"] = custo_hoje
    estado["dia_da_ultima_coleta"] = dia_semana_hoje
    salvar_estado(estado)
    
    # 4. PREPARAÇÃO DO CACHE PARA O FRONTEND
    # O Semanal é: Tudo que acumulamos nos dias passados + o que gastamos até agora hoje
    data["custo_semanal_acumulado"] = estado["total_acumulado_semana"] + custo_hoje
    r.set("cache_lovable", json.dumps(data))

    print(f"✅ Redis Atualizado. Hoje: R$ {custo_hoje:.2f} | Semanal: R$ {data['custo_semanal_acumulado']:.2f}")
    return {"status": "sucesso"}

# ====================================================================
# ENDPOINT: CONSULTA DA LOVABLE (GET /api/custos/)
# ====================================================================
@app.get("/api/custos/")
async def get_custos_financeiros():
    cache = r.get("cache_lovable")
    
    if not cache:
        return {
            "saldo_atual": "Carregando...",
            "custo_diario": "0.00",
            "custo_semanal": "0.00",
            "data_coleta": datetime.now().isoformat()
        }

    return processar_dados_para_dashboard_formatado(json.loads(cache))

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
        login_crm=data.get('login_crm', 'DASHBOARD_LOVABLE')
    )
    return upload_result

@app.get("/api/logs/")
async def get_logs():
    return [{"timestamp": datetime.now().strftime('%H:%M:%S'), "acao": "Sincronização", "regiao": "REDIS", "status": "Ativo", "registros": 0}]



