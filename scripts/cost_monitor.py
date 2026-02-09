import redis
import os
import sys

# Configura o Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://default:BMetYritSRFXIbozyBtCQpJpQKOxnnZE@redis.railway.internal:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

def iniciar_receptor():
    print("--- MONITOR DE CUSTOS (RECEPTOR ATIVO) ---", flush=True)
    pubsub = r.pubsub()
    pubsub.subscribe("logs_financeiro")
    
    # O loop fica esperando mensagens chegarem do seu PC via Gateway
    for message in pubsub.listen():
        if message['type'] == 'message':
            # Isso fará o log aparecer na aba 'Deploy Logs' do CUSTOS-MONITOR!
            print(f"[PC-LOCAL] {message['data']}", flush=True)

if __name__ == "__main__":
    iniciar_receptor()



































