# cost_scheduler.py (Versão com nome de função preservado)

import time
import subprocess
import sys
from datetime import datetime, time as dt_time

# 30 minutos em segundos (seu valor original)
INTERVALO_VERIFICACAO = 1800 

def should_run_now():
    """
    Nova lógica: Retorna True se for Seg-Sex entre 10h e 18h.
    """
    now = datetime.now()
    # weekday() <= 4 garante que é Segunda a Sexta
    is_weekday = now.weekday() <= 4
    # Verifica se está entre 10:00 e 17:59
    is_business_time = 10 <= now.hour < 18
    
    return is_weekday and is_business_time

def run_worker():
    print(f"[{datetime.now().strftime('%d/%m %H:%M:%S')}] 🚀 Iniciando scraping de custos...")
    try:
        # Chama o seu script de monitoramento
        subprocess.run([sys.executable, "scripts/cost_monitor.py"], check=True)
    except Exception as e:
        print(f"❌ Erro no worker: {e}")

if __name__ == "__main__":
    print("Agendador de Custos iniciado no Railway...")
    
    # --- GATILHO DE VISUALIZAÇÃO IMEDIATA ---
    run_worker() 
    # ----------------------------------------

    while True:
        # Aqui a função should_run_now agora checa a JANELA e não mais a HORA FIXA
        if should_run_now():
            run_worker()
            print(f"💤 Ciclo comercial completo. Aguardando 30 min...")
            time.sleep(INTERVALO_VERIFICACAO)
        else:
            # Se estiver fora do horário, espera 10 min antes de checar de novo
            print(f"[{datetime.now().strftime('%H:%M')}] Fora do horário comercial. Dormindo...")
            time.sleep(600)


