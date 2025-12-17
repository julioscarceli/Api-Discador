# scripts/monitor.py

import asyncio
import json
import re
from playwright.async_api import async_playwright
# Importamos as funções que agora usam o parâmetro 'server'
from utils.login_manager import create_context_and_login, get_base_url, get_login_url, get_server_name


# A URL de monitoramento direta (ch.php) é construída dinamicamente
def get_monitor_url(server: str):
    # CORREÇÃO DE PROTOCOLO: Usa o mesmo protocolo do LOGIN_URL
    login_url = get_login_url(server)
    return login_url.replace('pages/login.php', 'pages/ch.php')


async def run_monitor(server: str): # Recebe o parâmetro 'server'
    async with async_playwright() as p:
        # 1. Recebe os 3 objetos
        context, page, browser = await create_context_and_login(p, server=server)

        if not context:
            return {"active_calls": -1, "status": "Login Falhou"}

        server_name = get_server_name(server)

        try:
            # --- Etapa 1: Navegação Pós-Login ---
            monitor_url = get_monitor_url(server)
            
            # Tolerância alta para o goto (lida com a lentidão e redirecionamento)
            await page.goto(monitor_url, wait_until='domcontentloaded', timeout=40000) 
            
            print(f"[{server_name}] Redirecionado com tolerância para: {monitor_url}")

            # --- Etapa 2: Extrair o número de Active Calls ---
            active_calls_element = page.locator('text=/active calls/').first
            await active_calls_element.wait_for(state='visible', timeout=20000) 
            full_text = await active_calls_element.inner_text()
            
            match = re.search(r'(\d+)\s+active calls', full_text)

            if match:
                active_calls_count = int(match.group(1))
            else:
                active_calls_count = 0

            print(f"[{server_name}] Active Calls Encontradas: {active_calls_count}")
            return {"active_calls": active_calls_count, "status": "OK"}

        except Exception as e:
            print(f"[{server_name}] ❌ Erro na extração ou navegação: {e}")
            return {"active_calls": -1, "status": f"Extração Falhou: {e}"}

        finally:
            if browser: # ✅ FECHA O BROWSER AQUI (Libera RAM)
                await browser.close()






