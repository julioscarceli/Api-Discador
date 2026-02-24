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
    now_min = now.hour * 60 + now.minute
    return (START_HOUR * 60 + START_MINUTE) <= now_min <= (END_HOUR * 60 + END_MINUTE)

def get_config_turno():
    agora = get_now_sp().time()
    
    # Turno 10:00 às 13:00
    if datetime.time(10, 0) <= agora < datetime.time(13, 0):
        return {"max": "14", "desc1": "12", "ciclo1": 5, "desc2": "10", "ciclo2": 6, "min": "8", "ciclo3": 10, "final_min": "8", "final_ciclo": 20}
    
    # Turno 13:00 às 15:00
    elif datetime.time(13, 0) <= agora < datetime.time(15, 0):
        return {"max": "14", "desc1": "10", "ciclo1": 5, "desc2": "8", "ciclo2": 5, "min": "6", "ciclo3": 8, "final_min": "6", "final_ciclo": 20}
    
    # Turno 15:00 às 16:30
    elif datetime.time(15, 0) <= agora < datetime.time(16, 30):
        return {"max": "14", "desc1": "12", "ciclo1": 5, "desc2": "10", "ciclo2": 10, "min": "8", "ciclo3": 7, "final_min": "8", "final_ciclo": 12}
    
    # Turno 16:30 às 18:00
    elif datetime.time(16, 30) <= agora <= datetime.time(18, 0):
        return {"max": "16", "desc1": "10", "ciclo1": 5, "desc2": "8", "ciclo2": 10, "min": "6", "ciclo3": 12, "final_min": "6", "final_ciclo": 20}
    
    return {"max": "14", "desc1": "12", "ciclo1": 5, "desc2": "10", "ciclo2": 10, "min": "8", "ciclo3": 12}

def get_total_seconds(tempo_str):
    try:
        partes = list(map(int, tempo_str.split(':')))
        if len(partes) == 3: return partes[0] * 3600 + partes[1] * 60 + partes[2]
        elif len(partes) == 2: return partes[0] * 60 + partes[1]
        return 0
    except: return 0

async def run_monitor():
    canal_atual = "DESCONHECIDO" 
    ciclos_estaveis = 0
    pausa_estabilizacao = 0 

    async with async_playwright() as p:
        print(f"🚀 [SOMA - SP] Sensor Ativado | Ajuste de Canais Corrigido", flush=True)
        
        context, page, browser = await create_context_and_login(p, server="SP")
        if not context: return

        try:
            now_dt = get_now_sp().time()
            conf = get_config_turno()
            
            # Lógica de Início Diferenciado
            valor_inicio = conf['max']
            if datetime.time(10, 0) <= now_dt < datetime.time(13, 30):
                valor_inicio = "14"
                print(f"⚙️ [STARTUP SP] Turno 10h: Iniciando em {valor_inicio}...", flush=True)
            elif datetime.time(15, 0) <= now_dt < datetime.time(16, 30):
                valor_inicio = "14"
                print(f"⚙️ [STARTUP SP] Turno 15h: Iniciando em {valor_inicio}...", flush=True)
            else:
                print(f"⚙️ [STARTUP SP] Garantindo potência inicial em {valor_inicio}...", flush=True)

            if await acao_ajustar_potencia(valor=valor_inicio, server="SP"):
                canal_atual = valor_inicio

            await page.goto(URL_FILAS_SP)
            btn_fila = page.locator('//*[@id="GridFilas"]/ul/li[2]/a').first
            await btn_fila.wait_for(state="attached", timeout=15000)
            await btn_fila.dispatch_event("click") 
            
            while True:
                now_dt = get_now_sp()
                now_str = now_dt.strftime('%H:%M:%S')
                conf = get_config_turno()

                if not is_within_operating_hours():
                    print(f"💤 [{now_str}] Monitor SP em repouso...", flush=True)
                    await asyncio.sleep(300); continue

                if r.get("lock_restart_sp") == "active":
                    print(f"🚧 [{now_str}] BLOQUEIO REDIS: Restarter ativo.", flush=True)
                    await asyncio.sleep(20); continue

                try:
                    await page.wait_for_selector("#Filas tbody tr", timeout=15000)
                    linhas = await page.locator("#Filas tbody tr").all()
                    agentes_livres_logs = []
                    ociosos_criticos = 0

                    for linha in linhas:
                        col = await linha.locator("td").all_inner_texts()
                        if len(col) >= 7 and "LIVRE" in col[3].upper():
                            nome, tempo = col[0].strip(), col[6].strip()
                            agentes_livres_logs.append(f"🟢 [LIVRE] {nome} | Ociosidade: {tempo}")
                            if get_total_seconds(tempo) >= 60:
                                ociosos_criticos += 1

                    if pausa_estabilizacao > 0:
                        print(f"⏳ [{now_str}] Aguardando estabilização ({pausa_estabilizacao}/2)...", flush=True)
                        pausa_estabilizacao -= 1
                        await asyncio.sleep(15); continue

                    print(f"\n--- Ciclo SP: {now_str} | Canais: {canal_atual} | Estabilidade: {ciclos_estaveis} | Turno Max: {conf['max']} ---", flush=True)
                    for log in agentes_livres_logs: print(log, flush=True)

                    if ociosos_criticos >= 2:
                        print(f"🔴 CRÍTICO: {ociosos_criticos} agentes ociosos. Retornando para {conf['max']}!", flush=True)
                        if await acao_ajustar_potencia(valor=conf['max'], server="SP"):
                            canal_atual, ciclos_estaveis, pausa_estabilizacao = conf['max'], 0, 2
                    else:
                        ciclos_estaveis += 1
                        print(f"🟢 NORMAL: Operação estável (Ciclo {ciclos_estaveis}).", flush=True)

                        if canal_atual == conf['max'] and ciclos_estaveis >= conf['ciclo1']:
                            print(f"📉 Estabilidade {conf['ciclo1']} ciclos. Descendo para {conf['desc1']}...", flush=True)
                            if await acao_ajustar_potencia(valor=conf['desc1'], server="SP"):
                                canal_atual, ciclos_estaveis, pausa_estabilizacao = conf['desc1'], 0, 1
                        
                        elif canal_atual == conf['desc1'] and ciclos_estaveis >= conf['ciclo2']:
                            print(f"📉 Estabilidade {conf['ciclo2']} ciclos. Descendo para {conf['desc2']}...", flush=True)
                            if await acao_ajustar_potencia(valor=conf['desc2'], server="SP"):
                                canal_atual, ciclos_estaveis, pausa_estabilizacao = conf['desc2'], 0, 1
                        
                        elif canal_atual == conf['desc2'] and ciclos_estaveis >= conf['ciclo3']:
                            alvo = conf.get('min')
                            print(f"📉 Estabilidade {conf['ciclo3']} ciclos. Descendo para {alvo}...", flush=True)
                            if await acao_ajustar_potencia(valor=alvo, server="SP"):
                                canal_atual, ciclos_estaveis, pausa_estabilizacao = alvo, 0, 1

                        elif canal_atual == conf.get('min') and 'final_ciclo' in conf and ciclos_estaveis >= conf['final_ciclo']:
                            print(f"📉 Estabilidade {conf['final_ciclo']} ciclos. Descendo para {conf['final_min']}...", flush=True)
                            if await acao_ajustar_potencia(valor=conf['final_min'], server="SP"):
                                canal_atual, ciclos_estaveis, pausa_estabilizacao = conf['final_min'], 0, 1
                except:
                    await page.reload(); await asyncio.sleep(5)

                await asyncio.sleep(10)
        finally:
            if browser: await browser.close()

if __name__ == "__main__":
    asyncio.run(run_monitor())
    
