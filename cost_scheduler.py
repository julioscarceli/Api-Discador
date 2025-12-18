# cost_scheduler.py

import time
import subprocess
import sys
from datetime import datetime, time as dt_time, timedelta

INTERVALO_VERIFICACAO = 1800  # 30 minutos

HORARIOS_ALVO = [
    dt_time(15, 0),
    dt_time(18, 30)
]

last_run_time = None

def should_run_now():
    global last_run_time
    now = datetime.now().time()

    if last_run_time and (datetime.now() - last_run_time).total_seconds() < INTERVALO_VERIFICACAO:
        return False

    is_near = any(t <= now <= (datetime.combine(datetime.today(), t) + timedelta(minutes=30)).time()
                  for t in HORARIOS_ALVO)

    if is_near:
        last_run_time = datetime.now()
        return True
    return False

def run_worker():
    print(f"[{datetime.now()}] 🚀 Iniciando scraping de custos (Execução Imediata)...")
    try:
        # Chama o script de monitoramento que agora envia via POST para a API
        subprocess.run([sys.executable, "scripts/cost_monitor.py"], check=True)
    except Exception as e:
        print(f"Erro no worker: {e}")

if __name__ == "__main__":
    print("Agendador de Custos iniciado no Railway...")
    
    # --- GATILHO DE VISUALIZAÇÃO IMEDIATA ---
    # Esta linha garante que o dashboard carregue os dados assim que o card sobe
    run_worker() 
    # ----------------------------------------

    while True:
        if should_run_now():
            run_worker()
        time.sleep(INTERVALO_VERIFICACAO)
