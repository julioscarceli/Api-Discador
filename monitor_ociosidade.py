import asyncio
import datetime
import os
import redis
import sys
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login
from scripts.checagem_saidas import acao_ajustar_potencia

# Configurações de Horário Comercial (Baseado no relógio de Brasília)
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
    """Retorna o horário atual ajustado para Brasília (UTC-3)."""
    return datetime.datetime.now() - datetime.timedelta(hours=3)

def is_within_operating_hours() -> bool:
    now = get_now_sp()
    if now.weekday() >= 5: return False
    curr = now.hour * 60 + now.minute
    return (START_HOUR * 60 + START_MINUTE) <= curr <= (END_HOUR * 60 + END_MINUTE)

def is_horario_pico():
    agora = get_now_sp().time()
    return datetime.time(14, 40) <= agora <= datetime.time(16, 30)

def get_total_seconds(tempo_str):
    try:
        partes = list(map(int, tempo_str.split(':')))
        if len(partes) == 3: return partes[0] * 3600 + partes[1] * 60 + partes[2]
        elif len(partes) == 2: return partes[0] * 60 + partes[1]
        return 0
    except: return 0

async def run_monitor():
    # FIXO DEFINIDO: 40
    canal_atual = "40" 
    ciclos_estaveis = 0
    pausa_estabilizacao =
