import asyncio
import datetime
import os
import redis
import sys
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login
from scripts.checagem_saidas import acao_ajustar_potencia

# Configurações Brasília (09:30 - 18:30)
START_HOUR, START_MINUTE = 9, 30
END_HOUR, END_MINUTE = 18, 30

try:
    from config.settings import LOGIN_URL_SP
    try:
        from config.settings import URL_FILAS_SP
    except ImportError:
        URL_FILAS_SP = LOGIN_URL_SP.replace("login.php", "filas.php")
except ImportError:
    URL_FILAS_SP = "https://186.194.50.149/azcall/pages/filas.php"

REDIS_URL = os.getenv("REDIS_URL", "redis://default:BMetYritSRFXIbozyBtCQpJpQKOxnnZE@redis.railway.internal:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

def get_now_sp():
    return datetime.datetime.now() - datetime.timedelta(hours=3)

def is_within_operating_hours() -> bool:
    now = get_now_sp()
    if now.weekday() >= 5: return False
    curr = now.hour * 60 + now.minute
    return (START_HOUR * 60 + START_MINUTE) <= curr <= (END_HOUR * 60 + END_MINUTE)

def get_config_turno():
    agora = get_now_sp().time()
    
    # Turno 10:00 às 13:30
    if datetime.time(10, 0) <= agora < datetime.time(13, 30):
        return {"max": "28", "desc1": "22", "ciclo1": 5, "desc2": "18", "ciclo2": 10, "min": "16", "ciclo3": 15}
    
    # Turno 13:30 às 14:00
    elif datetime.time(13, 30) <= agora < datetime.time(14, 0):
        return {"max": "24", "desc1": "18", "ciclo1": 10, "desc2": "16", "ciclo2": 15, "min": "14", "ciclo3": 25}
    
    # Turno 15:00 às 16:30
    elif datetime.time(15, 0) <= agora < datetime.time(16, 30):
        return {"max": "26", "desc1": "20", "ciclo1": 5, "desc2": "18", "ciclo2": 10, "min": "16", "ciclo3": 10}
    
    # Turno 16:30 às 18:00
    elif datetime.time(16, 30) <= agora <= datetime.time(18, 0):
        return {"max": "28", "desc1": "24", "ciclo1": 5, "desc2": "18", "ciclo2": 10, "min": "16", "ciclo3": 10}
    
    return {"max": "24", "desc1": "20", "ciclo1": 10, "desc2": "18", "ciclo2": 10, "min": "16", "ciclo3": 10}

async def run_monitor():
    canal_atual = "DESCONHECIDO" 
    ciclos_estaveis = 0
    pausa_estabilizacao = 0 

    async with async_playwright() as p:
        print(f"🚀 [SOMA - SP] Monitor Ativado | Ajustes 23/02 Aplicados", flush=True)
        context, page, browser = await create_context_and_login(p, server="SP")
        if not context: return

        try:
            conf = get_config_turno()
            if await acao_ajustar_potencia(valor=conf['max'], server="SP"):
                canal_atual = conf['max']

            await page.goto(URL_FILAS_SP)
            btn_fila = page.locator('//*[@id="GridFilas"]/ul/li[2]/a').first
            await btn_fila.dispatch_event("click") 
            
            while True:
                now_str = get_now_sp().strftime('%H:%M:%S')
                conf = get_config_turno()

                if not is_within_operating_hours():
                    await asyncio.sleep(300); continue

                try:
                    await page.wait_for_selector("#Filas tbody tr", timeout=15000)
                    linhas = await page.locator("#Filas tbody tr").all()
                    ociosos_criticos = 0

                    for linha in linhas:
                        col = await linha.locator("td").all_inner_texts()
                        if len(col) >= 7 and "LIVRE" in col[3].upper():
                            tempo = col[6].strip()
                            partes = list(map(int, tempo.split(':')))
                            segundos = partes[0]*3600 + partes[1]*60 + partes[2] if len(partes)==3 else partes[0]*60 + partes[1]
                            if segundos >= 60: ociosos_criticos += 1

                    if pausa_estabilizacao > 0:
                        pausa_estabilizacao -= 1
                        await asyncio.sleep(15); continue

                    if ociosos_criticos >= 2:
                        if await acao_ajustar_potencia(valor=conf['max'], server="SP"):
                            canal_atual, ciclos_estaveis, pausa_estabilizacao = conf['max'], 0, 2
                    else:
                        ciclos_estaveis += 1
                        if canal_atual == conf['max'] and ciclos_estaveis >= conf['ciclo1']:
                            if await acao_ajustar_potencia(valor=conf['desc1'], server="SP"):
                                canal_atual, ciclos_estaveis, pausa_estabilizacao = conf['desc1'], 0, 1
                        elif canal_atual == conf['desc1'] and ciclos_estaveis >= conf['ciclo2']:
                            if await acao_ajustar_potencia(valor=conf['desc2'], server="SP"):
                                canal_atual, ciclos_estaveis, pausa_estabilizacao = conf['desc2'], 0, 1
                        elif canal_atual == conf['desc2'] and ciclos_estaveis >= conf['ciclo3']:
                            if await acao_ajustar_potencia(valor=conf['min'], server="SP"):
                                canal_atual, ciclos_estaveis, pausa_estabilizacao = conf['min'], 0, 1
                except:
                    await page.reload(); await asyncio.sleep(5)
                await asyncio.sleep(10)
        finally:
            if browser: await browser.close()

if __name__ == "__main__":
    asyncio.run(run_monitor())
    
