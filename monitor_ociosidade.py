# monitor_ociosidade.py (RAIZ)
import asyncio
import datetime
import os
import redis
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login
from scripts.checagem_saidas import acao_ajustar_potencia
from config.settings import LOGIN_URL_SP

# Conexão Redis usando URL oficial do seu Railway
REDIS_URL = os.getenv("REDIS_URL", "redis://default:BMetYritSRFXIbozyBtCQpJpQKOxnnZE@redis.railway.internal:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

def is_horario_pico():
    agora = datetime.datetime.now().time()
    return datetime.time(14, 40) <= agora <= datetime.time(16, 30)

def time_to_seconds(time_str):
    try:
        parts = list(map(int, time_str.split(':')))
        return parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1]
    except: return 0

async def run_monitor():
    canal_atual, ciclos_estaveis, pausa_estabilizacao = "DESCONHECIDO", 0, 0

    async with async_playwright() as p:
        print(f"🚀 Sensor de Ociosidade Ativado | Escada 36-32-26")
        context, page, browser = await create_context_and_login(p, server="SP")
        if not context: return

        try:
            await page.goto("https://186.194.50.149/azcall/pages/filas.php")
            await page.locator('//*[@id="GridFilas"]/ul/li[2]/a').first.click()

            while True:
                # 🛑 CHECAGEM DO SEMÁFORO REDIS (Evita conflito com Restarter)
                if r.get("lock_restart_sp") == "active":
                    print(f"🚧 BLOQUEIO: Restarter operando no SP. Aguardando 20s...")
                    await asyncio.sleep(20)
                    continue

                if is_horario_pico():
                    if canal_atual != "38":
                        if await acao_ajustar_potencia(valor="38"): canal_atual = "38"
                    await asyncio.sleep(20)
                else:
                    if pausa_estabilizacao > 0:
                        print(f"⏳ Aguardando estabilização ({pausa_estabilizacao}/2)...")
                        pausa_estabilizacao -= 1
                        await asyncio.sleep(15); continue

                    print(f"--- Ciclo: {datetime.datetime.now().strftime('%H:%M:%S')} | Canais: {canal_atual} | Estabilidade: {ciclos_estaveis}/20 ---")
                    await page.wait_for_selector("#Filas tbody tr", timeout=15000)
                    linhas = await page.locator("#Filas tbody tr").all()
                    ociosos_criticos = 0

                    for linha in linhas:
                        col = await linha.locator("td").all_inner_texts()
                        if len(col) >= 7 and "LIVRE" in col[3].upper():
                            if time_to_seconds(col[6].strip()) >= 60: ociosos_criticos += 1

                    if ociosos_criticos >= 3:
                        print(f"🔴 CRÍTICO: Ajustando para 36...")
                        if await acao_ajustar_potencia(valor="36"):
                            canal_atual, ciclos_estaveis, pausa_estabilizacao = "36", 0, 2
                    else:
                        ciclos_estaveis += 1
                        if canal_atual == "36" and ciclos_estaveis >= 20:
                            if await acao_ajustar_potencia(valor="32"): 
                                canal_atual, ciclos_estaveis, pausa_estabilizacao = "32", 0, 1
                        elif canal_atual == "32" and ciclos_estaveis >= 20:
                            if await acao_ajustar_potencia(valor="26"): 
                                canal_atual, ciclos_estaveis, pausa_estabilizacao = "26", 0, 1

                await asyncio.sleep(10)
        finally:
            if browser: await browser.close()

if __name__ == "__main__": asyncio.run(run_monitor())
