# main.py
import asyncio
import time
import datetime
import sys
from scripts.monitor import run_monitor
from scripts.restart_campaign import restart_campaign
from scripts.daily_mailing_worker import run_daily_import_pipeline

SERVERS_TO_MONITOR = ["MG", "SP"]
CHECK_INTERVAL_SECONDS = 15
falhas_login_consecutivas = 0

START_HOUR = 12
START_MINUTE = 30
END_HOUR = 21
END_MINUTE = 30

DAILY_IMPORT_HOUR = 11
DAILY_IMPORT_MINUTE = 00

def is_within_operating_hours() -> bool:
    now = datetime.datetime.now()
    if now.weekday() >= 5:
        return False
    current_time_minutes = now.hour * 60 + now.minute
    start_time_minutes = START_HOUR * 60 + START_MINUTE
    end_time_minutes = END_HOUR * 60 + END_MINUTE
    return start_time_minutes <= current_time_minutes <= end_time_minutes

async def check_and_act(server: str):
    result = await run_monitor(server=server)
    active_calls = result.get("active_calls", -1)
    status = result.get("status", "ERRO")
    print(f"[{server}] Resultado: {active_calls} active calls. Status: {status}")

    # AJUSTADO: Se as chamadas forem iguais ou menores que 6, aciona o restart
    if active_calls <= 6 and status == "OK":
        print(f"🚨 ALERTA [{server}]: Chamadas em nível crítico ({active_calls}). Acionando ROTINA DE RESTART...")
        success = await restart_campaign(server=server)
        if success:
            print(f"✅ RESTART SUCESSO [{server}]: Campanha reimportada e subida.")
        else:
            print(f"❌ RESTART FALHA [{server}]: Falha na rotina de reimportação.")
    return status

async def main_scheduler():
    global falhas_login_consecutivas
    while True:
        now = datetime.datetime.now()
        if now.hour == DAILY_IMPORT_HOUR and now.minute == DAILY_IMPORT_MINUTE and now.weekday() < 5:
            await run_daily_import_pipeline(server="MG")
            await run_daily_import_pipeline(server="SP")
            await asyncio.sleep(60)
        if is_within_operating_hours():
            status_mg = await check_and_act(server="MG")
            status_sp = await check_and_act(server="SP")
            if status_mg == "Login Falhou" and status_sp == "Login Falhou":
                falhas_login_consecutivas += 1
            else:
                falhas_login_consecutivas = 0
            if falhas_login_consecutivas >= 2:
                sys.exit(1)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == '__main__':
    asyncio.run(main_scheduler())









