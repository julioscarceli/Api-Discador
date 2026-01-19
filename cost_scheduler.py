# cost_scheduler.py (ATUALIZADO PARA FUSO HORÁRIO BRASÍLIA)

import time
import subprocess
import sys
from datetime import datetime

# Intervalo de 30 minutos em segundos
INTERVALO_VERIFICACAO = 1800 

def should_run_now():
    """
    Verifica se o horário atual (em UTC) corresponde à janela 
    das 10:00 às 18:00 de Brasília (UTC-3).
    """
    now = datetime.utcnow() # Usamos UTC explicitamente para evitar confusão
    
    # 1. Dia da semana (Segunda a Sexta)
    if now.weekday() >= 5:
        return False
        
    # 2. Janela de Horário:
    # 10:00 BRT -> 13:00 UTC
    # 18:00 BRT -> 21:00 UTC
    hora_utc = now.hour
    
    if 13 <= hora_utc < 21:
        return True
        
    return False

def run_worker():
    # ... (sua função run_worker original sem alterações)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Executando coleta...")
    try:
        subprocess.run([sys.executable, "scripts/cost_monitor.py"], check=True)
    except Exception as e:
        print(f"Erro no worker: {e}")

if __name__ == "__main__":
    print("Agendador de Custos (Fuso Brasília) Iniciado...")
    
    # Execução inicial para popular o dashboard
    run_worker() 

    while True:
        if should_run_now():
            run_worker()
            print(f"💤 Aguardando 30 minutos...")
            time.sleep(INTERVALO_VERIFICACAO)
        else:
            # Cálculo apenas para exibição no log de Brasília
            hora_brt = (datetime.utcnow().hour - 3) % 24
            print(f"[{hora_brt:02d}:{datetime.utcnow().minute:02d}] Fora do horário comercial. Dormindo...")
            time.sleep(600) # Checa a cada 10 min



