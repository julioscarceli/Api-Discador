# scripts/restart_campaign.py

import asyncio
import re
import os
from playwright.async_api import async_playwright

# --- CONFIGURAÇÕES VIA RAILWAY ---
DISCADOR_USER = os.getenv("DISCADOR_USER", "SOMA")
DISCADOR_PASS = os.getenv("DISCADOR_PASS", "123456")
HEADLESS = os.getenv("HEADLESS_MODE", "True").lower() == "true"
SAIDAS_VALOR = "100"

URL_DA_SP = "https://186.194.50.149/azcall/pages/da.php"
URL_DA_MG = "http://186.194.50.155/azcall/pages/da.php"

async def select_dropdown_option_forced(page, button_xpath, text_to_find, server_label, is_telefone=False):
    """
    Usa seletores de precisão para garantir a seleção mesmo em modo Headless.
    """
    try:
        await page.locator(button_xpath).click()
        await page.wait_for_timeout(1500)

        if is_telefone:
            # Seletores de precisão validados localmente
            js_path_telefone = "#Discador > div:nth-child(1) > div > div > div > div:nth-child(2) > div:nth-child(2) > div:nth-child(3) > div > div > div > ul > li:nth-child(2) > a"
            full_xpath_span = "/html/body/div[1]/div[2]/div[1]/div/form/div/div/div/div/div/div[1]/form/div[1]/div/div/div/div[2]/div[1]/div[3]/div/div/div/ul/li[2]/a/span[1]"
            
            # Clique via JS Path primeiro (mais robusto em headless)
            await page.evaluate(f'document.querySelector("{js_path_telefone}").click()')
            # Clique redundante via Full XPath para garantir
            await page.locator(f"xpath={full_xpath_span}").dispatch_event("click")
        else:
            # Lógica padrão para demais dropdowns
            option_link = page.locator('div.dropdown-menu.open ul li a').filter(has_text=text_to_find).first
            await option_link.locator('span.text').first.dispatch_event("click")
            
        await page.wait_for_timeout(1000)
        await page.keyboard.press("Enter")
        await page.keyboard.press("Tab")
        return True
    except Exception as e:
        print(f"[{server_label}] Erro no dropdown: {e}")
        return False

async def restart_campaign(server: str):
    """Executa o fluxo de restart otimizado para Railway."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        url_alvo = URL_DA_SP if server == "SP" else URL_DA_MG
        fila_name = "DISCADOR_SP" if server == "SP" else "DISCADOR_MG"

        try:
            print(f"[{server}] Iniciando restart via Railway...")
            await page.goto(url_alvo, timeout=60000)

            # --- LOGIN ---
            user_input = page.locator('input[name="user"], input[placeholder*="Usuá"]').first
            if await user_input.is_visible(timeout=10000):
                await user_input.fill(DISCADOR_USER)
                await page.locator('input[type="password"]').fill(DISCADOR_PASS)
                await page.locator('button:has-text("ENTRAR")').click()
                await page.wait_for_load_state("networkidle")

            # --- ABA ENVIAR ---
            await page.locator('a[data-toggle="tab"]:has-text("Enviar")').dispatch_event("click")
            await page.wait_for_timeout(3000)

            # --- IDENTIFICAÇÃO ---
            await page.wait_for_selector(".card-stats", state="visible", timeout=20000)
            stats_text = await page.locator(".card-stats").inner_text()
            match = re.search(r'MAILING_DISCADOR[^\s\n\r\-]+', stats_text)
            
            if not match:
                return False

            current_campaign = match.group(0).strip()
            print(f"[{server}] Campanha Detectada: {current_campaign}")

            # --- FINALIZAÇÃO ---
            await page.locator('button.btParar').first.dispatch_event("click")
            await page.locator('button.swal2-confirm').click()
            await page.wait_for_timeout(5000)

            # --- RECONFIGURAÇÃO ---
            # 1. Campanha
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[2]/div/div/button', current_campaign, server)

            # 2. Telefone (O ponto corrigido!)
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[3]/div/div/button', current_campaign, server, is_telefone=True)

            # 3. Fila
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[6]/div/div[1]/button', fila_name, server)

            # --- DISPARO FINAL ---
            await page.locator("#saida").fill(SAIDAS_VALOR)
            await page.wait_for_timeout(1000)
            await page.locator("#btCampanha1").dispatch_event("click")

            print(f"[{server}] ✅ RESTART CONCLUÍDO COM SUCESSO.")
            return True

        except Exception as e:
            print(f"❌ Erro Railway: {e}")
            return False
        finally:
            await browser.close()

if __name__ == '__main__':
    # No Railway, o servidor é passado dinamicamente
    target_server = os.getenv("TARGET_SERVER", "SP")
    asyncio.run(restart_campaign(server=target_server))






























