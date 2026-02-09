# cost_scheduler.py (VERSÃO CORRIGIDA)
import time
import subprocess
import sys
from datetime import datetime

# Intervalo de 30 minutos em segundos
INTERVALO_VERIFICACAO = 1800 

def should_run_now():
    now = datetime.utcnow()
    if now.weekday() >= 5:
        return False
    # Janela 10h-18h Brasília (13h-21h UTC)
    if 13 <= now.hour < 21:
        return True
    return False

def run_worker():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Disparando processo de coleta...", flush=True)
    try:
        # O parâmetro -u força o log a aparecer sem delay no Railway
        subprocess.run(
            [sys.executable, "-u", "scripts/cost_monitor.py"], 
            capture_output=False, 
            text=True,
            check=True
        )
    except Exception as e:
        print(f"❌ Erro no scheduler: {e}", flush=True)

if __name__ == "__main__":
    print("Agendador de Custos Iniciado...", flush=True)
    
    # Executa uma vez ao iniciar
    run_worker() 

    while True:
        if should_run_now():
            run_worker()
            print(f"💤 Aguardando 30 minutos...", flush=True)
            time.sleep(INTERVALO_VERIFICACAO)
        else:
            hora_brt = (datetime.utcnow().hour - 3) % 24
            print(f"[{hora_brt:02d}:{datetime.utcnow().minute:02d}] Fora do horário comercial. Dormindo...", flush=True)
            time.sleep(600)





