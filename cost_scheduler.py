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
        # CORREÇÃO AQUI: Removido 'scripts/' pois o arquivo está na raiz
        subprocess.run(
            [sys.executable, "-u", "cost_monitor.py"], 
            check=True,
            bufsize=0 
        )
    except Exception as e:
        print(f"❌ Erro no processo filho: {e}", flush=True)

if __name__ == "__main__":
    print("--- Agendador de Custos Iniciado ---", flush=True)
    
    # Opcional: Remova o run_worker() daqui se quiser que ele respeite 
    # apenas a função should_run_now() desde o início.
    run_worker() 

    while True:
        if should_run_now():
            run_worker()
            print(f"💤 Aguardando 30 min...", flush=True)
            time.sleep(INTERVALO_VERIFICACAO)
        else:
            # Se fora do horário, espera 10 min e checa o relógio de novo
            time.sleep(600)







