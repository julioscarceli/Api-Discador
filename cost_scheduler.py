# cost_scheduler.py
import time
import subprocess
import sys
import os
from datetime import datetime

INTERVALO_VERIFICACAO = 1800 

def should_run_now():
    # Janela 10h-18h Brasília (13h-21h UTC)
    now = datetime.utcnow()
    return now.weekday() < 5 and 13 <= now.hour < 21

def run_worker():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Iniciando coleta...", flush=True)
    
    # Define o caminho exato baseado na estrutura do seu GitHub
    # O arquivo está em scripts/cost_monitor.py
    script_path = os.path.join(os.getcwd(), "scripts", "cost_monitor.py")
    
    try:
        print(f"🔍 Tentando executar: {script_path}", flush=True)
        subprocess.run(
            [sys.executable, "-u", script_path], 
            check=True,
            bufsize=0 
        )
    except Exception as e:
        print(f"❌ Erro ao executar o monitor: {e}", flush=True)

if __name__ == "__main__":
    print("--- Agendador de Custos Iniciado ---", flush=True)
    
    # Execução inicial
    run_worker() 

    while True:
        if should_run_now():
            run_worker()
            print(f"💤 Aguardando 30 min...", flush=True)
            time.sleep(INTERVALO_VERIFICACAO)
        else:
            print(f"😴 Fora do horário. Verificando novamente em 10 min...", flush=True)
            time.sleep(600)










