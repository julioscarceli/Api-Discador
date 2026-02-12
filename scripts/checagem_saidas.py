# scripts/checagem_saidas.py
import asyncio
import os
from playwright.async_api import async_playwright

async def acao_ajustar_potencia(valor: str, server: str = "SP"):
    """Ajusta canais via dispatch_event para evitar erros de interceptação."""
    DISCADOR_USER = os.getenv("DISCADOR_USER", "SOMA")
    DISCADOR_PASS = os.getenv("DISCADOR_PASS", "123456")
    HEADLESS = os.getenv("HEADLESS_MODE", "True").lower() == "true"
    URL_ALVO = "https://186.194.50.149/azcall/pages/da.php" if server == "SP" else "http://186.194.50.155/azcall/pages/da.php"

    async with async_playwright() as p:
        print(f"🚀 [{server}] Ajustando para {valor} canais...")
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()
        # Bloqueia CSS/Imagens para performance na nuvem
        await page.route("**/*.{png,jpg,jpeg,css}", lambda route: route.abort())

        try:
            await page.goto(URL_ALVO, wait_until="commit", timeout=60000)
            
            # Login manual rápido para evitar dependências circulares
            user_input = page.locator('input[name="user"], input[placeholder*="Usuá"]').first
            await user_input.wait_for(state="visible", timeout=10000)
            await user_input.fill(DISCADOR_USER)
            await page.locator('input[type="password"]').fill(DISCADOR_PASS)
            await page.locator('button:has-text("ENTRAR")').click()
            
            # Navegação Aba Enviar via JS (Evita erro de menu interceptando clique)
            aba = page.locator('a[data-toggle="tab"]:has-text("Enviar")').first
            await aba.wait_for(state="attached", timeout=30000)
            await aba.dispatch_event("click") 
            
            # Clique no ícone de Saídas (Canais)
            btn_saidas = page.locator('i[onclick*="editsaidas"]').first
            await btn_saidas.wait_for(state="visible")
            await btn_saidas.click(force=True) 
            
            # Seleção no Modal
            await page.wait_for_selector(".swal2-modal", state="visible")
            await page.locator("#input-field").select_option(value=valor)
            
            # Confirmação forçada
            await page.locator('button.swal2-confirm:has-text("OK")').click(force=True)
            print(f"✅ [{server}] Sucesso: {valor} canais.")
            return True
        except Exception as e:
            print(f"❌ Erro Ajuste: {e}")
            return False
        finally:
            await browser.close()
