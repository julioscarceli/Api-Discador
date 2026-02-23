import redis
import os
import sys

# Configura o Redis usando a variável de ambiente do Railway
REDIS_URL = os.getenv("REDIS_URL", "redis://default:BMetYritSRFXIbozyBtCQpJpQKOxnnZE@redis.railway.internal:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

def iniciar_receptor():
    print("--- MONITOR DE CUSTOS (RECEPTOR ATIVO) ---", flush=True)
    pubsub = r.pubsub()
    pubsub.subscribe("logs_financeiro")
    
    # Loop contínuo que aguarda mensagens do Redis
    for message in pubsub.listen():
        if message['type'] == 'message':
            # O log aparecerá instantaneamente nos 'Deploy Logs' do Railway
            print(f"[PC-LOCAL] {message['data']}", flush=True)

def processar_dados_para_dashboard_formatado(dados):
    """Formata os valores para exibição no Dashboard."""
    try:
        saldo = dados.get("saldo_atual", 0.0)
        custo_diario = dados.get("custo_diario_total", 0.0)
        
        return {
            "saldo_atual": f"R$ {saldo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "custo_diario": f"R$ {custo_diario:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "custo_semanal": "R$ 0,00",
            "data_coleta": dados.get("data_coleta", "")
        }
    except Exception as e:
        return {"erro": str(e)}
        
if __name__ == "__main__":
    iniciar_receptor()





































