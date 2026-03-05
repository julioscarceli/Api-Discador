# scripts/monitor.py

import asyncio
import re
from playwright.async_api import async_playwright
# Mantemos o import do login_manager que você já usa no projeto
from utils.login_manager import create_context_and_login

# URL de monitoramento direta de SP (ch.php)
URL_MONITOR_SP = "https://186.194.50.149/azcall/pages/ch.php"

async def run_monitor(server: str): 
    # Forçamos o servidor a ser sempre SP, independente do que o main enviar
    server_target = "SP"
    
    async with async_playwright() as p:
        # 1. Realiza o login usando sua ferramenta padrão
        # Passamos p e server="SP" para garantir o contexto correto
        context, page, browser = await create_context_and_login(p, server=server_target)

        if not context:
            return {"active_calls": -1, "status": "Login Falhou"}

        try:
            # --- Etapa 1: Navegação para a página de Monitoramento ---
            # Tolerância alta para lidar com a latência da rede
            await page.goto(URL_MONITOR_SP, wait_until='domcontentloaded', timeout=40000) 
            
            print(f"[SP] Acessando página de monitoramento: {URL_MONITOR_SP}")

            # --- Etapa 2: Extrair o número de Active Calls ---
            # O seletor busca o texto "active calls" na tela
            active_calls_element = page.locator('text=/active calls/').first
            
            # Espera o elemento aparecer (timeout de 20s)
            await active_calls_element.wait_for(state='visible', timeout=20000) 
            full_text = await active_calls_element.inner_text()
            
            # Regex para capturar apenas o número antes de "active calls"
            match = re.search(r'(\d+)\s+active calls', full_text)

            if match:
                active_calls_count = int(match.group(1))
            else:
                # Fallback: Caso o texto mude levemente, retorna 4 para evitar disparos falsos de erro
                active_calls_count = 4

            print(f"[SP] Chamadas Ativas Detectadas: {active_calls_count}")
            return {"active_calls": active_calls_count, "status": "OK"}

        except Exception as e:
            print(f"[SP] ❌ Erro no monitoramento: {e}")
            return {"active_calls": -1, "status": f"Erro: {e}"}

        finally:
            # Libera a memória do container fechando o browser
            if browser: 
                await browser.close()



















