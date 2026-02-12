import asyncio
import datetime
import os
import redis
import sys
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login
from scripts.checagem_saidas import acao_ajustar_potencia

# Tratamento de Importação para evitar Crash no Railway
try:
    from config.settings import LOGIN_URL_SP
    try:
        from config.settings import URL_FILAS_SP
    except ImportError:
        URL_FILAS_SP = LOGIN_URL_SP.replace("login.php", "filas.php")
except ImportError as e:
    print(f"❌ Erro de configuração: {e}", flush=True)
    URL_FILAS_SP = "https://186.194.50.149/azcall/pages/filas.php"

# Conexão Redis
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
        print(f"🚀 [SOMA] Sensor Ativado | Escada: 36->32->26 | Pico (14:40-16:30): 38 fixo", flush=True)
        
        context, page, browser = await create_context_and_login(p, server="SP")
        if not context: return

        try:
            await page.goto(URL_FILAS_SP)
            btn_fila = page.locator('//*[@id="GridFilas"]/ul/li[2]/a').first
            await btn_fila.wait_for(state="attached", timeout=15000)
            await btn_fila.dispatch_event("click") 
            
            while True:
                now_str = datetime.datetime.now().strftime('%H:%M:%S')

                if r.get("lock_restart_sp") == "active":
                    print(f"🚧 [{now_str}] BLOQUEIO REDIS: Restarter operando no SP. Aguardando...", flush=True)
                    await asyncio.sleep(20)
                    continue

                if is_horario_pico():
                    if canal_atual != "38":
                        print(f"\n⚡ [HORÁRIO DE PICO] {now_str} | Forçando 38 canais...", flush=True)
                        if await acao_ajustar_potencia(valor="38", server="SP"): 
                            canal_atual = "38"; ciclos_estaveis = 0; pausa_estabilizacao = 2
                    else:
                        print(f"\n🟢 [PICO ATIVO] {now_str} | Mantendo 38 canais.", flush=True)
                    await asyncio.sleep(20)
                else:
                    if pausa_estabilizacao > 0:
                        print(f"⏳ [{now_str}] Aguardando estabilização do sistema ({pausa_estabilizacao}/2)...", flush=True)
                        pausa_estabilizacao -= 1
                        await asyncio.sleep(15); continue

                    # LOG DE INÍCIO DE CICLO (IGUAL AO LOCAL)
                    print(f"\n--- Ciclo: {now_str} | Canais: {canal_atual} | Estabilidade: {ciclos_estaveis}/20 ---", flush=True)
                    
                    try:
                        await page.wait_for_selector("#Filas tbody tr", timeout=15000)
                        linhas = await page.locator("#Filas tbody tr").all()
                        
                        agentes_livres_logs = []
                        ociosos_criticos = 0

                        for linha in linhas:
                            col = await linha.locator("td").all_inner_texts()
                            if len(col) >= 7 and "LIVRE" in col[3].upper():
                                nome, tempo_str = col[0].strip(), col[6].strip()
                                agentes_livres_logs.append(f"🟢 [LIVRE] {nome} | Ociosidade: {tempo_str}")
                                if time_to_seconds(tempo_str) >= 60:
                                    ociosos_criticos += 1

                        # IMPRESSÃO DOS AGENTES (IGUAL AO LOCAL)
                        for log in agentes_livres_logs: 
                            print(log, flush=True)

                        if ociosos_criticos >= 3:
                            print(f"🔴 CRÍTICO: {ociosos_criticos} agentes ociosos. Subindo para 36 canais!", flush=True)
                            if await acao_ajustar_potencia(valor="36", server="SP"):
                                canal_atual, ciclos_estaveis, pausa_estabilizacao = "36", 0, 2
                        else:
                            ciclos_estaveis += 1
                            print(f"🟢 NORMAL: Operação estável (Ciclo {ciclos_estaveis}).", flush=True)

                            if canal_atual == "36" and ciclos_estaveis >= 20:
                                print("📉 Estabilidade detectada. Descendo para 32 canais...", flush=True)
                                if await acao_ajustar_potencia(valor="32", server="SP"):
                                    canal_atual, ciclos_estaveis, pausa_estabilizacao = "32", 0, 1
                            elif canal_atual == "32" and ciclos_estaveis >= 20:
                                print("📉 Operação consolidada. Descendo para 26 canais...", flush=True)
                                if await acao_ajustar_potencia(valor="26", server="SP"):
                                    canal_atual, ciclos_estaveis, pausa_estabilizacao = "26", 0, 1
                    
                    except Exception as e_inner:
                        print(f"⚠️ Erro na leitura: {e_inner}. Recarregando...", flush=True)
                        await page.reload()
                        await asyncio.sleep(5)

                await asyncio.sleep(10)
        finally:
            if browser: await browser.close()

if __name__ == "__main__":
    asyncio.run(run_monitor())
