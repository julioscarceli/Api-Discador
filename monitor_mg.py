import asyncio
import datetime
import os
import redis
import sys
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login
from scripts.checagem_saidas import acao_ajustar_potencia

# Trava de Horário Comercial
START_HOUR, START_MINUTE = 12, 30
END_HOUR, END_MINUTE = 21, 30

try:
    from config.settings import LOGIN_URL_MG
    URL_FILAS_MG = LOGIN_URL_MG.replace("login.php", "filas.php")
except ImportError:
    URL_FILAS_MG = "http://186.194.50.155/azcall/pages/filas.php"

REDIS_URL = os.getenv("REDIS_URL", "redis://default:BMetYritSRFXIbozyBtCQpJpQKOxnnZE@redis.railway.internal:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

def is_within_operating_hours() -> bool:
    now = datetime.datetime.now()
    if now.weekday() >= 5: return False
    curr = now.hour * 60 + now.minute
    return (START_HOUR * 60 + START_MINUTE) <= curr <= (END_HOUR * 60 + END_MINUTE)

def is_horario_pico():
    agora = datetime.datetime.now().time()
    return datetime.time(14, 40) <= agora <= datetime.time(16, 30)

def get_total_seconds(tempo_str):
    try:
        partes = list(map(int, tempo_str.split(':')))
        if len(partes) == 3: return partes[0] * 3600 + partes[1] * 60 + partes[2]
        elif len(partes) == 2: return partes[0] * 60 + partes[1]
        return 0
    except: return 0

async def run_monitor():
    canal_atual = "40" 
    ciclos_estaveis = 0
    pausa_estabilizacao = 0 

    async with async_playwright() as p:
        print(f"🚀 [SOMA - MG] Monitor Ativado | Escada: 40->36->28 | Pico: 45 fixo", flush=True)
        
        context, page, browser = await create_context_and_login(p, server="MG")
        if not context: return

        try:
            await page.goto(URL_FILAS_MG)
            btn_fila = page.locator('//*[@id="GridFilas"]/ul/li[2]/a').first
            await btn_fila.wait_for(state="attached", timeout=15000)
            await btn_fila.dispatch_event("click") 
            
            while True:
                now_dt = datetime.datetime.now()
                now_str = now_dt.strftime('%H:%M:%S')

                if not is_within_operating_hours():
                    print(f"💤 [{now_str}] Monitor MG em repouso...", flush=True)
                    await asyncio.sleep(300); continue

                if r.get("lock_restart_mg") == "active":
                    print(f"🚧 [{now_str}] BLOQUEIO REDIS: Restarter ativo MG.", flush=True)
                    await asyncio.sleep(20); continue

                if is_horario_pico():
                    if canal_atual != "45":
                        print(f"\n⚡ [HORÁRIO DE PICO MG] {now_str} | Forçando 45 canais...", flush=True)
                        if await acao_ajustar_potencia(valor="45", server="MG"): 
                            canal_atual, ciclos_estaveis, pausa_estabilizacao = "45", 0, 2
                    else:
                        print(f"\n🟢 [PICO ATIVO MG] {now_str} | Mantendo 45 canais.")
                    await asyncio.sleep(20)
                else:
                    if pausa_estabilizacao > 0:
                        print(f"⏳ [{now_str}] MG: Aguardando estabilização do sistema ({pausa_estabilizacao}/2)...", flush=True)
                        pausa_estabilizacao -= 1
                        await asyncio.sleep(15); continue

                    print(f"\n--- Ciclo MG: {now_str} | Canais: {canal_atual} | Estabilidade: {ciclos_estaveis}/20 ---", flush=True)
                    
                    try:
                        await page.wait_for_selector("#Filas tbody tr", timeout=15000)
                        linhas = await page.locator("#Filas tbody tr").all()
                        agentes_livres_logs = []
                        ociosos_criticos = 0

                        for linha in linhas:
                            col = await linha.locator("td").all_inner_texts()
                            if len(col) >= 7 and "LIVRE" in col[3].upper():
                                nome, tempo = col[0].strip(), col[6].strip()
                                agentes_livres_logs.append(f"🟢 [MG - LIVRE] {nome} | Ociosidade: {tempo}")
                                if get_total_seconds(tempo) >= 60:
                                    ociosos_criticos += 1

                        for log in agentes_livres_logs: print(log, flush=True)

                        if ociosos_criticos >= 3:
                            print(f"🔴 CRÍTICO: {ociosos_criticos} agentes ociosos. Ajustando para 40!", flush=True)
                            if await acao_ajustar_potencia(valor="40", server="MG"):
                                canal_atual, ciclos_estaveis, pausa_estabilizacao = "40", 0, 2
                        else:
                            ciclos_estaveis += 1
                            print(f"🟢 NORMAL MG: Operação estável (Ciclo {ciclos_estaveis}).", flush=True)

                            if canal_atual == "40" and ciclos_estaveis >= 20:
                                print("📉 MG: Descendo para 36 canais...", flush=True)
                                if await acao_ajustar_potencia(valor="36", server="MG"):
                                    canal_atual, ciclos_estaveis, pausa_estabilizacao = "36", 0, 1
                            elif canal_atual == "36" and ciclos_estaveis >= 20:
                                print("📉 MG: Descendo para 28 canais...", flush=True)
                                if await acao_ajustar_potencia(valor="28", server="MG"):
                                    canal_atual, ciclos_estaveis, pausa_estabilizacao = "28", 0, 1
                    except:
                        await page.reload(); await asyncio.sleep(5)

                await asyncio.sleep(10)
        finally:
            if browser: await browser.close()

if __name__ == "__main__":
    asyncio.run(run_monitor())
