# cost_scheduler.py
import time
import subprocess
import sys
from datetime import datetime

INTERVALO_VERIFICACAO = 1800 

def should_run_now():
    now = datetime.utcnow()
    # Janela 10h-18h Brasília (13h-21h UTC)
    return now.weekday() < 5 and 13 <= now.hour < 21

def run_worker():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Iniciando coleta...", flush=True)
    try:
        # TENTATIVA 1: Se o arquivo estiver dentro da pasta scripts
        # Altere para "scripts/cost_monitor.py" se for o caso
        subprocess.run(
            [sys.executable, "-u", "scripts/cost_monitor.py"], 
            check=True,
            bufsize=0 
        )
    except Exception as e:
        print(f"❌ Erro no processo filho: {e}", flush=True)
        # TENTATIVA 2 (Backup): Se a primeira falhar, tenta na raiz (caso você mova o arquivo)
        if "No such file" in str(e):
             print("🔍 Tentando localizar na raiz...", flush=True)
             try:
                 subprocess.run([sys.executable, "-u", "cost_monitor.py"], check=True)
             except: pass

if __name__ == "__main__":
    print("--- Agendador de Custos Iniciado ---", flush=True)
    run_worker() 

    while True:
        if should_run_now():
            run_worker()
            print(f"💤 Aguardando 30 min...", flush=True)
            time.sleep(INTERVALO_VERIFICACAO)
        else:
            time.sleep(600)









