import asyncio
import datetime
import os
import redis
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login
from scripts.checagem_saidas import acao_ajustar_potencia
from config.settings import LOGIN_URL_SP  # Importando apenas o que existe no settings.py

# Conexão Redis usando a URL do seu Railway
REDIS_URL = os.getenv("REDIS_URL", "redis://default:BMetYritSRFXIbozyBtCQpJpQKOxnnZE@redis.railway.internal:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

# Construção dinâmica da URL de Filas para evitar erro de importação
URL_FILAS_SP = LOGIN_URL_SP.replace("login.php", "filas.php")

def is_horario_pico():
    """Regra: 14:40 às 16:30 -> 38 canais fixos."""
    agora = datetime.datetime.now().time()
    return datetime.time(14, 40) <= agora <= datetime.time(16, 30)

def time_to_seconds(time_str):
    try:
        parts = list(map(int, time_str.split(':')))
        return parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1]
    except: return 0

async def run_monitor():
    canal_atual = "DESCONHECIDO"
    ciclos_estaveis = 0
    pausa_estabilizacao = 0 

    async with async_playwright() as p:
        print(f"🚀 Sensor Ativado | Escada: 36->32->26 | Headless: {os.getenv('HEADLESS_MODE', 'True')}")
        
        # 🔑 Login Unificado via LoginManager (Melhoria: Usa sua função padrão)
        context, page, browser = await create_context_and_login(p, server="SP")
        if not context: 
            print("❌ Falha no login inicial. Abortando monitor.")
            return

        try:
            # Navegação para a Fila SP usando a URL construída dinamicamente
            await page.goto(URL_FILAS_SP)
            
            # Melhoria: Clique forçado via JS para evitar interceptação de menus superiores
            btn_fila = page.locator('//*[@id="GridFilas"]/ul/li[2]/a').first
            await btn_fila.wait_for(state="attached", timeout=15000)
            await btn_fila.dispatch_event("click") 
            
            while True:
                now = datetime.datetime.now().strftime('%H:%M:%S')

                # 🛑 CHECAGEM DO SEMÁFORO REDIS (Evita conflito com o main.py/restarter)
                if r.get("lock_restart_sp") == "active":
                    print(f"🚧 [{now}] BLOQUEIO: Restarter operando no SP. Aguardando 20s...")
                    await asyncio.sleep(20)
                    continue

                if is_horario_pico():
                    if canal_atual != "38":
                        if await acao_ajustar_potencia(valor="38", server="SP"): 
                            canal_atual = "38"; ciclos_estaveis = 0; pausa_estabilizacao = 2
                    else:
                        print(f"🟢 [{now}] Pico Ativo: Mantendo 38 canais.")
                    await asyncio.sleep(20)
                else:
                    # Melhoria: Pausa de Estabilização (2 ciclos após ações críticas)
                    if pausa_estabilizacao > 0:
                        print(f"⏳ [{now}] Aguardando estabilização do sistema ({pausa_estabilizacao}/2)...")
                        pausa_estabilizacao -= 1
                        await asyncio.sleep(15); continue

                    print(f"--- Ciclo: {now} | Canais: {canal_atual} | Estabilidade: {ciclos_estaveis}/20 ---")
                    
                    await page.wait_for_selector("#Filas tbody tr", timeout=15000)
                    linhas = await page.locator("#Filas tbody tr").all()
                    ociosos_criticos = 0

                    for linha in linhas:
                        col = await linha.locator("td").all_inner_texts()
                        if len(col) >= 7 and "LIVRE" in col[3].upper():
                            if time_to_seconds(col[6].strip()) >= 60: ociosos_criticos += 1

                    # Melhoria: Escada 36 -> 32 -> 26 com 20 ciclos de espera
                    if ociosos_criticos >= 3:
                        print(f"🔴 CRÍTICO: {ociosos_criticos} agentes ociosos. Ajustando para 36...")
                        if await acao_ajustar_potencia(valor="36", server="SP"):
                            canal_atual, ciclos_estaveis, pausa_estabilizacao = "36", 0, 2
                    else:
                        ciclos_estaveis += 1
                        if canal_atual == "36" and ciclos_estaveis >= 20:
                            print("📉 Estabilidade atingida em 36. Descendo para 32...")
                            if await acao_ajustar_potencia(valor="32", server="SP"):
                                canal_atual, ciclos_estaveis, pausa_estabilizacao = "32", 0, 1
                        elif canal_atual == "32" and ciclos_estaveis >= 20:
                            print("📉 Estabilidade atingida em 32. Descendo para 26...")
                            if await acao_ajustar_potencia(valor="26", server="SP"):
                                canal_atual, ciclos_estaveis, pausa_estabilizacao = "26", 0, 1

                await asyncio.sleep(10)
        finally:
            if browser: await browser.close()

if __name__ == "__main__":
    asyncio.run(run_monitor())
