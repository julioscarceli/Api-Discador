# scripts/checagem_saidas.py
import asyncio
import os
from playwright.async_api import async_playwright
# Importa as configurações centralizadas
from config.settings import LOGIN_URL_SP, LOGIN_URL_MG

async def acao_ajustar_potencia(valor: str, server: str = "SP"):
    """
    Ajusta a potência (canais) no discador.
    Utiliza dispatch_event e force=True para evitar erros de interceptação no Railway.
    """
    # Credenciais lidas das variáveis de ambiente do Railway
    DISCADOR_USER = os.getenv("DISCADOR_USER", "SOMA")
    DISCADOR_PASS = os.getenv("DISCADOR_PASS", "123456")
    HEADLESS = os.getenv("HEADLESS_MODE", "True").lower() == "true"
    
    # Define a URL alvo (DA) baseada no login do servidor correspondente
    base_login_url = LOGIN_URL_SP if server.upper() == "SP" else LOGIN_URL_MG
    URL_ALVO = base_login_url.replace("login.php", "da.php")

    async with async_playwright() as p:
        print(f"🚀 [{server}] Ajustando Potência para: {valor} canais...")
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()
        
        # Bloqueia CSS/Imagens para performance e economia de recursos na nuvem
        await page.route("**/*.{png,jpg,jpeg,css}", lambda route: route.abort())

        try:
            # 1. Navegação e Login
            await page.goto(URL_ALVO, wait_until="commit", timeout=60000)
            
            # Localizador resiliente conforme usado localmente
            user_input = page.locator('input[name="user"], input[placeholder*="Usuá"]').first
            await user_input.wait_for(state="visible", timeout=10000)
            
            await user_input.fill(DISCADOR_USER)
            await page.locator('input[type="password"]').fill(DISCADOR_PASS)
            await page.locator('button:has-text("ENTRAR")').click()
            
            # Garante carregamento pós-login
            if "da.php" not in page.url:
                await page.goto(URL_ALVO, wait_until="domcontentloaded")

            # 2. Acesso à Aba Enviar (Forçado para evitar interceptação de menu)
            aba = page.locator('a[data-toggle="tab"]:has-text("Enviar")').first
            await aba.wait_for(state="attached", timeout=30000)
            await aba.dispatch_event("click") 
            await page.wait_for_selector(".card-stats", state="visible", timeout=30000)

            # 3. Clique no ícone de Saídas (Canais)
            btn_saidas = page.locator('i[onclick*="editsaidas"]').first
            await btn_saidas.wait_for(state="visible", timeout=15000)
            await btn_saidas.click(force=True) 

            # 4. Manipulação do Modal (SWAL2)
            await page.wait_for_selector(".swal2-modal", state="visible", timeout=10000)
            select_field = page.locator("#input-field")
            await select_field.select_option(value=valor)
            await page.wait_for_timeout(1000)

            # 5. Confirmação Final
            confirm_btn = page.locator('button.swal2-confirm:has-text("OK")')
            await confirm_btn.click(force=True)
            await page.wait_for_selector(".swal2-modal", state="hidden", timeout=10000)

            print(f"✅ [{server}] SUCESSO: Potência ajustada para {valor} canais.")
            return True

        except Exception as e:
            print(f"❌ Erro no ajuste de potência [{server}]: {e}")
            return False
        finally:
            await browser.close()
