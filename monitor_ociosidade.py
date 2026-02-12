import asyncio
import datetime
import os
import redis
import sys
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login
from scripts.checagem_saidas import acao_ajustar_potencia

# Configurações de Horário (Igual ao seu main.py)
START_HOUR, START_MINUTE = 12, 30
END_HOUR, END_MINUTE = 21, 30

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

def is_within_operating_hours() -> bool:
    now = datetime.datetime.now()
    if now.weekday() >= 5: return False  # Sáb/Dom não roda
    curr = now.hour * 60 + now.minute
    return (START_HOUR * 60 + START_MINUTE) <= curr <= (END_HOUR * 60 + END_MINUTE)

def is_horario_pico():
    agora = datetime.datetime.now().time()
    return datetime.time(14, 40) <= agora <= datetime.time(16, 30)

async def run_monitor():
    canal_atual = "DESCONHECIDO"
    ciclos_estaveis = 0
    pausa_estabilizacao = 0 

    async with async_playwright() as p:
        print(f"🚀 [SOMA - SP] Monitor Iniciado com Trava de Horário Comercial.", flush=True)
        
        context, page, browser = await create_context_and_login(p, server="SP")
        if not context: return

        try:
            await page.goto(URL_FILAS_SP)
            btn_fila = page.locator('//*[@id="GridFilas"]/ul/li[2]/a').first
            await btn_fila.wait_for(state="attached", timeout=15000)
            await btn_fila.dispatch_event("click") 
            
            while True:
                now_str = datetime.datetime.now().strftime('%H:%M:%S')

                # 🛑 TRAVA DE HORÁRIO COMERCIAL
                if not is_within_operating_hours():
                    print(f"💤 [{now_str}] Fora do horário de expediente. Monitor SP em repouso...", flush=True)
                    await asyncio.sleep(300) # Dorme 5 minutos antes de checar de novo
                    continue

                if r.get("lock_restart_sp") == "active":
                    print(f"🚧 [{now_str}] BLOQUEIO REDIS: Restarter operando no SP.", flush=True)
                    await asyncio.sleep(20); continue

                if is_horario_pico():
                    if canal_atual != "38":
                        if await acao_ajustar_potencia(valor="38", server="SP"): 
                            canal_atual, ciclos_estaveis, pausa_estabilizacao = "38", 0, 2
                    await asyncio.sleep(20)
                else:
                    if pausa_estabilizacao > 0:
                        pausa_estabilizacao -= 1
                        await asyncio.sleep(15); continue

                    print(f"\n--- Ciclo SP: {now_str} | Canais: {canal_atual} | Estabilidade: {ciclos_estaveis}/20 ---", flush=True)
                    
                    try:
                        await page.wait_for_selector("#Filas tbody tr", timeout=15000)
                        linhas = await page.locator("#Filas tbody tr").all()
                        ociosos_criticos = 0

                        for linha in linhas:
                            col = await linha.locator("td").all_inner_texts()
                            if len(col) >= 7 and "LIVRE" in col[3].upper():
                                nome, tempo = col[0].strip(), col[6].strip()
                                print(f"🟢 [LIVRE] {nome} | Ociosidade: {tempo}", flush=True)
                                # Lógica de segundos simplificada aqui para brevidade
                                if ":" in tempo and int(tempo.split(':')[-2]) >= 1: ociosos_criticos += 1

                        if ociosos_criticos >= 3:
                            if await acao_ajustar_potencia(valor="36", server="SP"):
                                canal_atual, ciclos_estaveis, pausa_estabilizacao = "36", 0, 2
                        else:
                            ciclos_estaveis += 1
                            if canal_atual == "36" and ciclos_estaveis >= 20:
                                if await acao_ajustar_potencia(valor="32", server="SP"):
                                    canal_atual, ciclos_estaveis, pausa_estabilizacao = "32", 0, 1
                            elif canal_atual == "32" and ciclos_estaveis >= 20:
                                if await acao_ajustar_potencia(valor="26", server="SP"):
                                    canal_atual, ciclos_estaveis, pausa_estabilizacao = "26", 0, 1
                    except:
                        await page.reload(); await asyncio.sleep(5)

                await asyncio.sleep(10)
        finally:
            if browser: await browser.close()

if __name__ == "__main__":
    asyncio.run(run_monitor())
