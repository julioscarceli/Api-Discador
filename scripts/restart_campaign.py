# scripts/restart_campaign.py

import asyncio
import re
import os
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login, get_fila_name, get_server_name

# --- CONFIGURAÇÕES VIA RAILWAY ---
DISCADOR_USER = os.getenv("DISCADOR_USER", "SOMA")
DISCADOR_PASS = os.getenv("DISCADOR_PASS", "123456")
HEADLESS = os.getenv("HEADLESS_MODE", "True").lower() == "true"
SAIDAS_VALOR = "100"

URL_DA_SP = "https://186.194.50.149/azcall/pages/da.php"
URL_DA_MG = "http://186.194.50.155/azcall/pages/da.php"

async def select_dropdown_option_forced(page, button_xpath, text_to_find, server_label, is_telefone=False):
    """Sincronização reforçada com cliques via JS para evitar Timeouts no Railway."""
    try:
        btn = page.locator(button_xpath)
        # Espera o botão estar no DOM antes de qualquer ação
        await btn.wait_for(state="attached", timeout=20000)
        await btn.dispatch_event("click") # Clique forçado para abrir o menu
        await page.wait_for_timeout(2000)

        if is_telefone:
            # Seletores de precisão validados localmente
            js_path_tel = "#Discador > div:nth-child(1) > div > div > div > div:nth-child(2) > div:nth-child(2) > div:nth-child(3) > div > div > div > ul > li:nth-child(2) > a"
            print(f"[{server_label}] Aplicando clique de precisão via JS no Telefone...")
            await page.evaluate(f'document.querySelector("{js_path_tel}").click()')
        else:
            option_link = page.locator('div.dropdown-menu.open ul li a').filter(has_text=text_to_find).first
            # Clica no span.text que é o alvo real visto no HTML
            await option_link.locator('span.text').first.dispatch_event("click")
            
        await page.wait_for_timeout(1000)
        await page.keyboard.press("Enter")
        await page.keyboard.press("Tab")
        return True
    except Exception as e:
        print(f"[{server_label}] ⚠️ Falha Dropdown: {e}")
        return False

async def finalize_campaign_only(server: str):
    """Função de limpeza exigida pelo api_server.py."""
    async with async_playwright() as p:
        context, page, browser = await create_context_and_login(p, server=server)
        if not context: return False
        try:
            await page.get_by_role("link", name="send Discador Automático").click()
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            # Espera a aba 'Enviar' estar pronta
            aba = page.locator('a[data-toggle="tab"]:has-text("Enviar")').first
            await aba.wait_for(state="attached", timeout=20000)
            await aba.dispatch_event("click")
            await page.wait_for_timeout(3000)
            # Finaliza
            await page.locator('button.btParar').first.dispatch_event("click")
            await page.locator('button.swal2-confirm').first.dispatch_event("click")
            return True
        finally:
            await browser.close()

async def restart_campaign(server: str):
    """Fluxo principal otimizado para a latência do Railway."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        url_alvo = URL_DA_SP if server == "SP" else URL_DA_MG
        fila_name = "DISCADOR_SP" if server == "SP" else "DISCADOR_MG"

        try:
            print(f"[{server}] Acessando URL Direta...")
            # wait_until="load" é mais rápido, mas o "networkidle" garante que o AJAX terminou
            await page.goto(url_alvo, wait_until="networkidle", timeout=60000)

            # --- LOGIN ---
            user_input = page.locator('input[name="user"], input[placeholder*="Usuá"]').first
            if await user_input.is_visible(timeout=5000):
                await user_input.fill(DISCADOR_USER)
                await page.locator('input[type="password"]').fill(DISCADOR_PASS)
                await page.locator('button:has-text("ENTRAR")').click()
                await page.wait_for_load_state("networkidle", timeout=45000)

            # --- ABA ENVIAR ---
            aba_enviar = page.locator('a[data-toggle="tab"]:has-text("Enviar")').first
            await aba_enviar.wait_for(state="attached", timeout=30000)
            await aba_enviar.dispatch_event("click")
            
            # Trava fundamental para evitar Timeout: espera os dados carregarem no card
            await page.wait_for_selector(".card-stats", state="visible", timeout=40000)

            # --- IDENTIFICAÇÃO ---
            stats_text = await page.locator(".card-stats").inner_text()
            match = re.search(r'MAILING_DISCADOR[^\s\n\r\-]+', stats_text)
            if not match: return False
            current_campaign = match.group(0).strip()
            print(f"[{server}] Campanha Detectada: {current_campaign}")

            # --- FINALIZAÇÃO ---
            await page.locator('button.btParar').first.dispatch_event("click")
            await page.locator('button.swal2-confirm').wait_for(state="visible", timeout=10000)
            await page.locator('button.swal2-confirm').click()
            await page.wait_for_timeout(5000)

            # --- RECONFIGURAÇÃO ---
            # 1. Campanha
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[2]/div/div/button', current_campaign, server)
            # 2. Telefone (Ponto Crítico)
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[3]/div/div/button', current_campaign, server, is_telefone=True)
            # 3. Fila
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[6]/div/div[1]/button', fila_name, server)

            # --- DISPARO FINAL ---
            await page.locator("#saida").fill(SAIDAS_VALOR)
            await page.wait_for_timeout(1000)
            await page.locator("#btCampanha1").dispatch_event("click")

            print(f"[{server}] ✅ RESTART EXECUTADO COM SUCESSO.")
            return True
        except Exception as e:
            print(f"❌ Erro Railway: {e}")
            return False
        finally:
            await browser.close()

if __name__ == '__main__':
    target_server = os.getenv("TARGET_SERVER", "SP")
    asyncio.run(restart_campaign(server=target_server))

































