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

# --- SELETORES CONSTANTES ---
SELETOR_TAB_ENVIAR = 'a[data-toggle="tab"]:has-text("Enviar")'
SELETOR_BOTAO_FINALIZAR = 'button.btParar'
SELETOR_CONFIRMAR_FINALIZAR = 'button.swal2-confirm'

async def select_dropdown_option_forced(page, button_xpath, text_to_find, server_label, is_telefone=False):
    """
    Usa seletores de precisão (JS Path e XPath) para garantir a seleção.
    """
    try:
        await page.locator(button_xpath).click()
        await page.wait_for_timeout(1500)

        if is_telefone:
            # Seletores de precisão validados localmente
            js_path_telefone = "#Discador > div:nth-child(1) > div > div > div > div:nth-child(2) > div:nth-child(2) > div:nth-child(3) > div > div > div > ul > li:nth-child(2) > a"
            full_xpath_span = "/html/body/div[1]/div[2]/div[1]/div/form/div/div/div/div/div/div[1]/form/div[1]/div/div/div/div[2]/div[1]/div[3]/div/div/div/ul/li[2]/a/span[1]"
            
            await page.evaluate(f'document.querySelector("{js_path_telefone}").click()')
            await page.locator(f"xpath={full_xpath_span}").dispatch_event("click")
        else:
            option_link = page.locator('div.dropdown-menu.open ul li a').filter(has_text=text_to_find).first
            await option_link.locator('span.text').first.dispatch_event("click")
            
        await page.wait_for_timeout(1000)
        await page.keyboard.press("Enter")
        await page.keyboard.press("Tab")
        return True
    except Exception as e:
        print(f"[{server_label}] Erro no dropdown: {e}")
        return False

async def finalize_campaign_only(server: str):
    """Restaura a função necessária para o api_server.py não dar erro de importação."""
    async with async_playwright() as p:
        context, page, browser = await create_context_and_login(p, server=server)
        if not context: return False
        try:
            await page.get_by_role("link", name="send Discador Automático").click()
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            # Clique forçado na aba enviar via JS
            await page.locator(SELETOR_TAB_ENVIAR).first.dispatch_event("click")
            await page.wait_for_timeout(3000)
            # Finaliza
            await page.locator(SELETOR_BOTAO_FINALIZAR).first.dispatch_event("click")
            await page.locator(SELETOR_CONFIRMAR_FINALIZAR).first.dispatch_event("click")
            return True
        finally:
            await browser.close()

async def restart_campaign(server: str):
    """Executa o fluxo de restart otimizado que resolve o problema do Telefone."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        url_alvo = URL_DA_SP if server == "SP" else URL_DA_MG
        fila_name = "DISCADOR_SP" if server == "SP" else "DISCADOR_MG"

        try:
            print(f"[{server}] Acessando URL Direta no Railway...")
            await page.goto(url_alvo, timeout=60000)

            # Login robusto usando variáveis do Railway
            user_input = page.locator('input[name="user"], input[placeholder*="Usuá"]').first
            if await user_input.is_visible(timeout=10000):
                await user_input.fill(DISCADOR_USER)
                await page.locator('input[type="password"]').fill(DISCADOR_PASS)
                await page.locator('button:has-text("ENTRAR")').click()
                await page.wait_for_load_state("networkidle")

            await page.locator(SELETOR_TAB_ENVIAR).dispatch_event("click")
            await page.wait_for_timeout(3000)

            # Identifica Campanha
            await page.wait_for_selector(".card-stats", state="visible", timeout=20000)
            stats_text = await page.locator(".card-stats").inner_text()
            match = re.search(r'MAILING_DISCADOR[^\s\n\r\-]+', stats_text)
            if not match: return False
            current_campaign = match.group(0).strip()

            # Finaliza antiga
            await page.locator(SELETOR_BOTAO_FINALIZAR).first.dispatch_event("click")
            await page.locator(SELETOR_CONFIRMAR_FINALIZAR).first.click()
            await page.wait_for_timeout(5000)

            # Reconfiguração (Ponto da correção do Telefone)
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[2]/div/div/button', current_campaign, server)
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[3]/div/div/button', current_campaign, server, is_telefone=True)
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[6]/div/div[1]/button', fila_name, server)

            # Disparo
            await page.locator("#saida").fill(SAIDAS_VALOR)
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































