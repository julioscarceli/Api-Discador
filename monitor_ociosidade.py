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
        return {"max": "16", "desc1": "12", "ciclo1": 5, "desc2": "10", "ciclo2": 6, "min": "8", "ciclo3": 10, "final_min": "8", "final_ciclo": 20}
    
    # Turno 13:00 às 15:00
    elif datetime.time(13, 0) <= agora < datetime.time(15, 0):
        return {"max": "16", "desc1": "10", "ciclo1": 5, "desc2": "8", "ciclo2": 5, "min": "6", "ciclo3": 8, "final_min": "6", "final_ciclo": 20}
    
    # Turno 15:00 às 16:30
    elif datetime.time(15, 0) <= agora < datetime.time(16, 30):
        return {"max": "16", "desc1": "12", "ciclo1": 5, "desc2": "10", "ciclo2": 10, "min": "8", "ciclo3": 7, "final_min": "8", "final_ciclo": 12}
    
    # Turno 16:30 às 18:00
    elif datetime.time(16, 30) <= agora <= datetime.time(18, 0):
        return {"max": "16", "desc1": "10", "ciclo1": 5, "desc2": "8", "ciclo2": 10, "min": "6", "ciclo3": 12, "final_min": "6", "final_ciclo": 20}
    
    return {"max": "16", "desc1": "12", "ciclo1": 5, "desc2": "10", "ciclo2": 10, "min": "8", "ciclo3": 12}

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
                valor_inicio = "16"
                print(f"⚙️ [STARTUP SP] Turno 10h: Iniciando em {valor_inicio}...", flush=True)
            elif datetime.time(15, 0) <= now_dt < datetime.time(16, 30):
                valor_inicio = "16"
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
                now_dt
    
