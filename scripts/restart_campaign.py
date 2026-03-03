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
SAIDAS_VALOR = "12"

URL_DA_SP = "https://186.194.50.149/azcall/pages/da.php"
URL_DA_MG = "http://186.194.50.155/azcall/pages/da.php"

# --- SELETORES ---
SELETOR_TAB_ENVIAR = 'a[data-toggle="tab"]:has-text("Enviar")'
SELETOR_BOTAO_FINALIZAR = 'button.btParar'
SELETOR_CONFIRMAR_FINALIZAR = 'button.swal2-confirm'
# SELETOR_AGRESSIVIDADE_BOTAO REMOVIDO CONFORME SOLICITADO

async def select_dropdown_option_forced(page, button_xpath, text_to_find, server_label, is_telefone=False):
    """Sincronização reforçada para garantir seleção em Headless."""
    try:
        btn = page.locator(button_xpath)
        await btn.wait_for(state="attached", timeout=20000)
        await btn.dispatch_event("click")
        await page.wait_for_timeout(2000)

        if is_telefone:
            # Seletores de precisão validados localmente
            js_path_tel = "#Discador > div:nth-child(1) > div > div > div > div:nth-child(2) > div:nth-child(2) > div:nth-child(3) > div > div > div > ul > li:nth-child(2) > a"
            await page.evaluate(f'document.querySelector("{js_path_tel}").click()')
        else:
            option_link = page.locator('div.dropdown-menu.open ul li a').filter(has_text=text_to_find).first
            await option_link.locator('span.text').first.dispatch_event("click")
            
        await page.wait_for_timeout(1000)
        await page.keyboard.press("Enter")
        await page.keyboard.press("Tab")
        return True
    except Exception as e:
        print(f"[{server_label}] ⚠️ Erro Dropdown: {e}")
        return False

async def finalize_campaign_only(server: str):
    """Finaliza a campanha ativa."""
    server_name = server.upper()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        url_alvo = URL_DA_SP if server_name == "SP" else URL_DA_MG

        try:
            print(f"[{server_name}] Finalizando: Acessando URL Direta...")
            await page.goto(url_alvo, wait_until="commit", timeout=60000)

            user_input = page.locator('input[name="user"], input[placeholder*="Usuá"]').first
            if await user_input.is_visible(timeout=5000):
                await user_input.fill(DISCADOR_USER)
                await page.locator('input[type="password"]').fill(DISCADOR_PASS)
                await page.locator('button:has-text("ENTRAR")').click()
                await page.wait_for_load_state("domcontentloaded", timeout=30000)

            if "da.php" not in page.url:
                print(f"[{server_name}] Desvio detectado ({page.url}). Forçando DA...")
                await page.goto(url_alvo, wait_until="domcontentloaded", timeout=45000)

            print(f"[{server_name}] Sincronizando aba Enviar...")
            aba = page.locator(SELETOR_TAB_ENVIAR).first
            await aba.wait_for(state="attached", timeout=30000)
            await aba.dispatch_event("click")
            
            await page.wait_for_selector(".card-stats", state="visible", timeout=30000)

            btn_finalizar = page.locator(SELETOR_BOTAO_FINALIZAR).first
            if await btn_finalizar.count() > 0:
                print(f"[{server_name}] 🖱️ Disparando Finalizar...")
                await btn_finalizar.dispatch_event("click")
                
                btn_confirmar = page.locator(SELETOR_CONFIRMAR_FINALIZAR).first
                await btn_confirmar.wait_for(state="attached", timeout=10000)
                await btn_confirmar.dispatch_event("click")
                
                await page.wait_for_timeout(5000)
                print(f"[{server_name}] ✅ Campanha FINALIZADA com sucesso.")
            else:
                print(f"[{server_name}] ℹ️ Campanha já estava parada.")

            return True

        except Exception as e:
            print(f"[{server_name}] ❌ Falha na finalização: {e}")
            return False
        finally:
            await browser.close()

async def restart_campaign(server: str):
    """Fluxo ultra-resiliente sem o clique na agressividade."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        url_alvo = URL_DA_SP if server == "SP" else URL_DA_MG
        fila_name = "DISCADOR_SP" if server == "SP" else "DISCADOR_MG"

        try:
            print(f"[{server}] Acessando URL Direta...")
            await page.goto(url_alvo, wait_until="commit", timeout=60000)

            user_input = page.locator('input[name="user"], input[placeholder*="Usuá"]').first
            if await user_input.is_visible(timeout=5000):
                await user_input.fill(DISCADOR_USER)
                await page.locator('input[type="password"]').fill(DISCADOR_PASS)
                await page.locator('button:has-text("ENTRAR")').click()
                await page.wait_for_load_state("domcontentloaded", timeout=30000)

            if "da.php" not in page.url:
                print(f"[{server}] Redirecionado para {page.url}. Forçando retorno para DA...")
                await page.goto(url_alvo, wait_until="domcontentloaded", timeout=45000)

            print(f"[{server}] Sincronizando aba Enviar...")
            aba = page.locator(SELETOR_TAB_ENVIAR).first
            await aba.wait_for(state="attached", timeout=45000)
            await aba.dispatch_event("click")
            
            await page.wait_for_selector(".card-stats", state="visible", timeout=30000)
            
            stats_text = await page.locator(".card-stats").inner_text()
            match = re.search(r'MAILING_DISCADOR[^\s\n\r\-]+', stats_text)
            if not match: return False
            current_campaign = match.group(0).strip()
            print(f"[{server}] Campanha Detectada: {current_campaign}")

            await page.locator(SELETOR_BOTAO_FINALIZAR).first.dispatch_event("click")
            await page.locator(SELETOR_CONFIRMAR_FINALIZAR).first.dispatch_event("click")
            await page.wait_for_timeout(5000)

            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[2]/div/div/button', current_campaign, server)
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[3]/div/div/button', current_campaign, server, is_telefone=True)
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[6]/div/div[1]/button', fila_name, server)

            # --- AQUI ESTAVA O CLIQUE NA AGRESSIVIDADE (REMOVIDO) ---
            
            print(f"[{server}] Disparando com {SAIDAS_VALOR} canais...")
            await page.locator("#saida").fill(SAIDAS_VALOR)
            await page.wait_for_timeout(1000)
            await page.locator("#btCampanha1").dispatch_event("click")

            await page.wait_for_timeout(8000)
            print(f"[{server}] ✅ RESTART CONCLUÍDO COM SUCESSO.")
            return True

        except Exception as e:
            if "Timeout" in str(e) and "btCampanha1" in str(e):
                print(f"[{server}] ✅ Sucesso detectado (Timeout ignorado após ação).")
                return True
            print(f"❌ Erro Railway: {e}")
            return False
        finally:
            await browser.close()

if __name__ == '__main__':
    target_server = os.getenv("TARGET_SERVER", "SP")
    asyncio.run(restart_campaign(server=target_server))

























































