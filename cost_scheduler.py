import time
import subprocess
import sys
from datetime import datetime

INTERVALO_VERIFICACAO = 1800 

def should_run_now():
    # Usa UTC para compatibilidade com o servidor Railway (13h-21h UTC = 10h-18h Brasília)
    now = datetime.utcnow()
    return now.weekday() < 5 and 13 <= now.hour < 21

def run_worker():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Iniciando coleta...", flush=True)
    try:
        # CORREÇÃO: Removido 'scripts/' pois o monitor está na raiz
        subprocess.run(
            [sys.executable, "-u", "cost_monitor.py"], 
            check=True,
            bufsize=0 
        )
    except Exception as e:
        print(f"❌ Erro no processo filho: {e}", flush=True)

if __name__ == "__main__":
    print("--- Agendador de Custos Iniciado ---", flush=True)
    
    # Tenta rodar imediatamente ao iniciar
    run_worker() 

    while True:
        if should_run_now():
            run_worker()
            print(f"💤 Aguardando 30 min...", flush=True)
            time.sleep(INTERVALO_VERIFICACAO)
        else:
            print(f"😴 Fora do horário de pico. Aguardando 10 min...", flush=True)
            time.sleep(600)








