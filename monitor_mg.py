import asyncio
import datetime
import os
import redis
import sys
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login
from scripts.checagem_saidas import acao_ajustar_potencia

# 1. Tratamento de Importação para MG (Mantendo sua estrutura)
try:
    from config.settings import LOGIN_URL_MG
    # Constrói a URL de filas de MG dinamicamente
    URL_FILAS_MG = LOGIN_URL_MG.replace("login.php", "filas.php")
except ImportError as e:
    print(f"❌ Erro de configuração MG: {e}", flush=True)
    URL_FILAS_MG = "http://186.194.50.155/azcall/pages/filas.php"

# 2. Conexão Redis
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
    canal_atual = "DESCONHECIDO"
    ciclos_estaveis = 0
    pausa_estabilizacao = 0 

    async with async_playwright() as p:
        print(f"🚀 [SOMA - MG] Sensor Ativado | Escada: 36->32->26 | Pico 38 fixo", flush=True)
        
        # 🔑 Login via LoginManager unificado para MG
        context, page, browser = await create_context_and_login(p, server="MG")
        if not context: 
            print("❌ Falha no login MG. Verifique credenciais.", flush=True)
            return

        try:
            await page.goto(URL_FILAS_MG)
            # Clique na aba da fila (Seletor padrão da SipPulse)
            btn_fila = page.locator('//*[@id="GridFilas"]/ul/li[2]/a').first
            await btn_fila.wait_for(state="attached", timeout=15000)
            await btn_fila.dispatch_event("click") 
            
            while True:
                now_str = datetime.datetime.now().strftime('%H:%M:%S')

                # 🛑 CHECAGEM DO SEMÁFORO REDIS ESPECÍFICO PARA MG
                if r.get("lock_restart_mg") == "active":
                    print(f"🚧 [{now_str}] BLOQUEIO REDIS (MG): Restarter operando. Aguardando...", flush=True)
                    await asyncio.sleep(20)
                    continue

                if is_horario_pico():
                    if canal_atual != "38":
                        print(f"\n⚡ [HORÁRIO DE PICO MG] {now_str} | Forçando 38 canais...", flush=True)
                        if await acao_ajustar_potencia(valor="38", server="MG"): 
                            canal_atual = "38"; ciclos_estaveis = 0; pausa_estabilizacao = 2
                    else:
                        print(f"\n🟢 [PICO ATIVO MG] {now_str} | Mantendo 38 canais.", flush=True)
                    await asyncio.sleep(20)
                else:
                    if pausa_estabilizacao > 0:
                        print(f"⏳ [{now_str}] MG: Estabilizando sistema ({pausa_estabilizacao}/2)...", flush=True)
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
                                nome, tempo_str = col[0].strip(), col[6].strip()
                                agentes_livres_logs.append(f"🟢 [MG - LIVRE] {nome} | Ociosidade: {tempo_str}")
                                if time_to_seconds(tempo_str) >= 60:
                                    ociosos_criticos += 1

                        for log in agentes_livres_logs: print(log, flush=True)

                        if ociosos_criticos >= 3:
                            print(f"🔴 CRÍTICO MG: {ociosos_criticos} ociosos. Subindo para 36!", flush=True)
                            if await acao_ajustar_potencia(valor="36", server="MG"):
                                canal_atual, ciclos_estaveis, pausa_estabilizacao = "36", 0, 2
                        else:
                            ciclos_estaveis += 1
                            print(f"🟢 NORMAL MG: Operação estável (Ciclo {ciclos_estaveis}).", flush=True)

                            if canal_atual == "36" and ciclos_estaveis >= 20:
                                print("📉 MG: Estabilidade atingida em 36. Descendo para 32...", flush=True)
                                if await acao_ajustar_potencia(valor="32", server="MG"):
                                    canal_atual, ciclos_estaveis, pausa_estabilizacao = "32", 0, 1
                            elif canal_atual == "32" and ciclos_estaveis >= 20:
                                print("📉 MG: Operação consolidada. Descendo para 26...", flush=True)
                                if await acao_ajustar_potencia(valor="26", server="MG"):
                                    canal_atual, ciclos_estaveis, pausa_estabilizacao = "26", 0, 1
                    
                    except Exception as e:
                        print(f"⚠️ Erro na leitura de MG: {e}. Recarregando...", flush=True)
                        await page.reload()
                        await asyncio.sleep(5)

                await asyncio.sleep(10)
        finally:
            if browser: await browser.close()

if __name__ == "__main__":
    asyncio.run(run_monitor())
