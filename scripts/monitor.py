# scripts/monitor.py
import asyncio
import re
import os
from playwright.async_api import async_playwright

# --- CONFIGURAÇÕES ---
DISCADOR_USER = os.getenv("DISCADOR_USER", "SOMA")
DISCADOR_PASS = os.getenv("DISCADOR_PASS", "123456")
HEADLESS = os.getenv("HEADLESS_MODE", "True").lower() == "true"

URL_DA_SP = "https://186.194.50.149/azcall/pages/da.php"
URL_DA_MG = "http://186.194.50.155/azcall/pages/da.php"

async def run_monitor(server: str):
    """
    Versão Estável: Captura chamadas ativas via regex no texto da página.
    """
    server_name = server.upper()
    url_alvo = URL_DA_SP if server_name == "SP" else URL_DA_MG
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        try:
            # Acesso à página
            await page.goto(url_alvo, wait_until="domcontentloaded", timeout=60000)

            # Login automático se cair na tela de login
            user_input = page.locator('input[name="user"]').first
            if await user_input.is_visible(timeout=5000):
                await user_input.fill(DISCADOR_USER)
                await page.locator('input[type="password"]').fill(DISCADOR_PASS)
                await page.locator('button:has-text("ENTRAR")').click()
                await page.wait_for_load_state("networkidle", timeout=30000)

            # Garante que está na página de discagem
            if "da.php" not in page.url:
                await page.goto(url_alvo, wait_until="domcontentloaded")

            # Aguarda os dados carregarem na tela
            await page.wait_for_timeout(5000)
            
            # Captura o texto total da página para busca via Regex
            page_text = await page.evaluate("() => document.body.innerText")
            
            # REGEX ESTÁVEL: Busca o padrão numérico de chamadas ativas
            # Procura por "Chamadas Ativas" seguido de números
            match = re.search(r'Chamadas\s+Ativas[:\s]+(\d+)', page_text, re.IGNORECASE)
            
            if match:
                active_calls = int(match.group(1))
            else:
                # Segunda tentativa: busca apenas números isolados que costumam ficar nos cards de topo
                # Seletor específico para o elemento de chamadas se o regex falhar
                try:
                    active_calls = int(await page.locator(".card-stats").first.inner_text())
                except:
                    active_calls = 0

            return {"active_calls": active_calls, "status": "OK"}

        except Exception as e:
            print(f"[{server_name}] ❌ Erro Monitor: {e}")
            if "login" in str(e).lower():
                return {"active_calls": -1, "status": "Login Falhou"}
            return {"active_calls": -1, "status": "ERRO"}
        finally:
            await browser.close()














