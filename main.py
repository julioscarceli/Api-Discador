# main.py (Scheduler Principal)

import asyncio
import time
import datetime
import sys
import os
import redis
from scripts.monitor import run_monitor
from scripts.restart_campaign import restart_campaign
from scripts.daily_mailing_worker import run_daily_import_pipeline

# --- CONFIGURAÇÃO REDIS ---
REDIS_URL = os.getenv("REDIS_URL", "redis://default:BMetYritSRFXIbozyBtCQpJpQKOxnnZE@redis.railway.internal:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

# Lista dos servidores que devem ser monitorados em cada ciclo
SERVERS_TO_MONITOR = ["MG", "SP"]
CHECK_INTERVAL_SECONDS = 15
falhas_login_consecutivas = 0

# --- HORÁRIO DE EXPEDIENTE (UTC/RAILWAY) ---
START_HOUR, START_MINUTE = 12, 30
END_HOUR, END_MINUTE = 21, 30
DAILY_IMPORT_HOUR, DAILY_IMPORT_MINUTE = 11, 00

def is_within_operating_hours() -> bool:
    now = datetime.datetime.now()
    if now.weekday() >= 5: return False
    current_time_minutes = now.hour * 60 + now.minute
    start_time_minutes = START_HOUR * 60 + START_MINUTE
    end_time_minutes = END_HOUR * 60 + END_MINUTE
    return start_time_minutes <= current_time_minutes <= end_time_minutes

async def check_and_act(server: str):
    """Executa o monitoramento e ativa o bloqueio Redis se necessário."""
    result = await run_monitor(server=server)
    active_calls = result.get("active_calls", -1)
    status = result.get("status", "ERRO")

    print(f"[{server}] Resultado: {active_calls} active calls. Status: {status}")

    if active_calls == 0 and status == "OK":
        # 🚩 ATIVA BLOQUEIO NO REDIS (Expira em 5 min por segurança)
        lock_key = f"lock_restart_{server.lower()}"
        r.setex(lock_key, 300, "active")
        print(f"🚨 ALERTA [{server}]: Chamadas zeradas. Bloqueando ociosidade e reiniciando...")

        success = await restart_campaign(server=server)

        if success:
            print(f"✅ RESTART SUCESSO [{server}]: Campanha reimportada.")
        else:
            print(f"❌ RESTART FALHA [{server}]")
        
        # 🏁 LIBERA O BLOQUEIO
        r.delete(lock_key)

    elif active_calls > 0:
        print(f"[{server}] Operação normal.")
    
    return status

async def main_scheduler():
    global falhas_login_consecutivas
    print("Iniciando Scheduler Principal (Modo Headless Railway)...")

    while True:
        now = datetime.datetime.now()

        # 1. Rotina Diária
        if now.hour == DAILY_IMPORT_HOUR and now.minute == DAILY_IMPORT_MINUTE and now.weekday() < 5:
            print("\n--- INICIANDO PIPELINE DE IMPORTAÇÃO DIÁRIA ---")
            await run_daily_import_pipeline(server="MG")
            await run_daily_import_pipeline(server="SP")
            await asyncio.sleep(60)

        # 2. Monitoramento Contínuo
        if is_within_operating_hours():
            status_mg = await check_and_act(server="MG")
            status_sp = await check_and_act(server="SP")

            if status_mg == "Login Falhou" and status_sp == "Login Falhou":
                falhas_login_consecutivas += 1
            else:
                falhas_login_consecutivas = 0

            if falhas_login_consecutivas >= 2:
                print("🚨 [CRITICAL] Falhas seguidas. Reiniciando container...")
                sys.exit(1)
        else:
            print(f"--- [INATIVO] Fora do Horário Comercial ---")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == '__main__':
    try:
        asyncio.run(main_scheduler())
    except KeyboardInterrupt:
        print("Scheduler encerrado.")







