# scripts/checagem_saidas.py
import asyncio
import os
from playwright.async_api import async_playwright

async def acao_ajustar_potencia(valor: str, server: str = "SP"):
    DISCADOR_USER = os.getenv("DISCADOR_USER", "SOMA")
    DISCADOR_PASS = os.getenv("DISCADOR_PASS", "123456")
    HEADLESS = os.getenv("HEADLESS_MODE", "True").lower() == "true"
    URL_ALVO = "https://186.194.50.149/azcall/pages/da.php" if server == "SP" else "http://186.194.50.155/azcall/pages/da.php"

    async with async_playwright() as p:
        print(f"🚀 [{server}] Ajustando Potência para: {valor} canais...")
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        try:
            await page.goto(URL_ALVO, wait_until="commit", timeout=60000)
            user_input = page.locator('input[name="user"], input[placeholder*="Usuá"]').first
            await user_input.wait_for(state="visible", timeout=10000)
            await user_input.fill(DISCADOR_USER)
            await page.locator('input[type="password"]').fill(DISCADOR_PASS)
            await page.locator('button:has-text("ENTRAR")').click()
            
            await page.locator('a[data-toggle="tab"]:has-text("Enviar")').first.dispatch_event("click")
            await page.locator('i[onclick*="editsaidas"]').first.click()
            await page.wait_for_selector(".swal2-modal", state="visible")
            await page.locator("#input-field").select_option(value=valor)
            await page.locator('button.swal2-confirm:has-text("OK")').click()
            return True
        except Exception as e:
            print(f"❌ Erro Ajuste: {e}")
            return False
        finally:
            await browser.close()
