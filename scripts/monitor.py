import asyncio
import os
import re
from playwright.async_api import async_playwright

# Configurações do Discador
DISCADOR_USER = os.getenv("DISCADOR_USER", "SOMA")
DISCADOR_PASS = os.getenv("DISCADOR_PASS", "123456")
HEADLESS = os.getenv("HEADLESS_MODE", "True").lower() == "true"

URL_SP = "https://186.194.50.149/azcall/pages/da.php"
URL_MG = "http://186.194.50.155/azcall/pages/da.php"

async def run_monitor(server: str):
    """
    Monitora o número de chamadas ativas.
    Retorna: {"active_calls": int, "status": str}
    """
    server_name = server.upper()
    url_alvo = URL_SP if server_name == "SP" else URL_MG
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        try:
            # Acesso à página
            await page.goto(url_alvo, wait_until="domcontentloaded", timeout=45000)

            # Login (se necessário)
            user_input = page.locator('input[name="user"]').first
            if await user_input.is_visible(timeout=5000):
                await user_input.fill(DISCADOR_USER)
                await page.locator('input[type="password"]').fill(DISCADOR_PASS)
                await page.locator('button:has-text("ENTRAR")').click()
                await page.wait_for_load_state("networkidle", timeout=30000)

            # Garantir que estamos na aba correta (da.php)
            if "da.php" not in page.url:
                await page.goto(url_alvo, wait_until="domcontentloaded")

            # Captura o texto de chamadas ativas (ajuste o seletor conforme seu HTML)
            # Geralmente fica dentro de um card de estatísticas
            content = await page.content()
            
            # Busca por padrões como "Chamadas Ativas: X" ou dentro de elementos específicos
            # Exemplo de extração via seletor de classe comum em Dashboards:
            calls_element = page.locator(".card-stats:has-text('Chamadas')").first
            if await calls_element.is_visible():
                text = await calls_element.inner_text()
                # Tenta extrair apenas os números
                match = re.search(r'(\d+)', text)
                active_calls = int(match.group(1)) if match else 0
            else:
                # Fallback: tenta buscar no texto geral da página se o seletor falhar
                match = re.search(r'Chamadas\s+Ativas[:\s]+(\d+)', content, re.IGNORECASE)
                active_calls = int(match.group(1)) if match else 0

            return {"active_calls": active_calls, "status": "OK"}

        except Exception as e:
            print(f"[{server_name}] Erro no monitoramento: {e}")
            if "Login" in str(e):
                return {"active_calls": -1, "status": "Login Falhou"}
            return {"active_calls": -1, "status": "ERRO"}
        finally:
            await browser.close()













