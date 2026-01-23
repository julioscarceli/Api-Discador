# scripts/restart_campaign.py

import asyncio
import re
import os
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login, get_fila_name, get_server_name

# --- CONFIGURAÇÕES RAILWAY ---
DISCADOR_USER = os.getenv("DISCADOR_USER", "SOMA")
DISCADOR_PASS = os.getenv("DISCADOR_PASS", "123456")
HEADLESS = os.getenv("HEADLESS_MODE", "True").lower() == "true"
SAIDAS_VALOR = "100"

URL_DA_SP = "https://186.194.50.149/azcall/pages/da.php"
URL_DA_MG = "http://186.194.50.155/azcall/pages/da.php"

# --- SELETORES ---
SELETOR_TAB_ENVIAR = 'a[data-toggle="tab"]:has-text("Enviar")'
SELETOR_BOTAO_FINALIZAR = 'button.btParar'
SELETOR_CONFIRMAR_FINALIZAR = 'button.swal2-confirm'

async def select_dropdown_option_forced(page, button_xpath, text_to_find, server_label, is_telefone=False):
    """Sincronização reforçada para evitar que o campo fique em branco."""
    try:
        btn = page.locator(button_xpath)
        await btn.wait_for(state="attached", timeout=20000)
        await btn.dispatch_event("click")
        await page.wait_for_timeout(1500)

        if is_telefone:
            # Seletores de precisão (JS Path) que mataram o problema localmente
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
        print(f"[{server_label}] ⚠️ Alerta Dropdown: {e}")
        return False

async def finalize_campaign_only(server: str):
    """Restaura a função para evitar o ImportError no deploy."""
    async with async_playwright() as p:
        context, page, browser = await create_context_and_login(p, server=server)
        if not context: return False
        try:
            await page.get_by_role("link", name="send Discador Automático").click()
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            await page.locator(SELETOR_TAB_ENVIAR).first.dispatch_event("click")
            await page.wait_for_timeout(3000)
            await page.locator(SELETOR_BOTAO_FINALIZAR).first.dispatch_event("click")
            await page.locator(SELETOR_CONFIRMAR_FINALIZAR).first.dispatch_event("click")
            return True
        except:
            return False
        finally:
            await browser.close()

async def restart_campaign(server: str):
    """Fluxo principal que ignora falsos erros de log no final."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        url_alvo = URL_DA_SP if server == "SP" else URL_DA_MG
        fila_name = "DISCADOR_SP" if server == "SP" else "DISCADOR_MG"

        try:
            print(f"[{server}] Acessando URL Direta no Railway...")
            await page.goto(url_alvo, wait_until="domcontentloaded", timeout=60000)

            # Login robusto
            user_input = page.locator('input[name="user"], input[placeholder*="Usuá"]').first
            if await user_input.is_visible(timeout=5000):
                await user_input.fill(DISCADOR_USER)
                await page.locator('input[type="password"]').fill(DISCADOR_PASS)
                try:
                    await page.locator('button:has-text("ENTRAR")').click(timeout=5000)
                except: pass
                await page.wait_for_load_state("networkidle", timeout=30000)

            # Ativa aba Enviar
            aba = page.locator(SELETOR_TAB_ENVIAR).first
            await aba.wait_for(state="attached", timeout=20000)
            await aba.dispatch_event("click")
            
            # Espera carregar o card para extrair nome
            await page.wait_for_selector(".card-stats", state="visible", timeout=40000)
            stats_text = await page.locator(".card-stats").inner_text()
            match = re.search(r'MAILING_DISCADOR[^\s\n\r\-]+', stats_text)
            if not match: return False
            current_campaign = match.group(0).strip()
            print(f"[{server}] Campanha Detectada: {current_campaign}")

            # Finaliza atual
            await page.locator(SELETOR_BOTAO_FINALIZAR).first.dispatch_event("click")
            try:
                confirm = page.locator(SELETOR_CONFIRMAR_FINALIZAR).first
                await confirm.wait_for(state="visible", timeout=5000)
                await confirm.click()
            except: pass
            await page.wait_for_timeout(5000)

            # Reconfiguração (A correção do Telefone!)
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[2]/div/div/button', current_campaign, server)
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[3]/div/div/button', current_campaign, server, is_telefone=True)
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[6]/div/div[1]/button', fila_name, server)

            # Disparo Final
            await page.locator("#saida").fill(SAIDAS_VALOR)
            await page.wait_for_timeout(1000)
            
            print(f"[{server}] Disparando mailing final...")
            # Ação final que costumava gerar o erro de log falso
            await page.locator("#btCampanha1").dispatch_event("click")
            
            # Espera técnica para o servidor processar o restart
            await page.wait_for_timeout(6000)
            print(f"[{server}] ✅ RESTART CONCLUÍDO COM SUCESSO.")
            return True

        except Exception as e:
            # MELHORIA NOS LOGS: Ignora o Timeout se ocorrer após o clique do aviãozinho
            if "Timeout" in str(e) and "btCampanha1" in str(e):
                print(f"[{server}] ✅ Sucesso (Redirecionamento pós-disparo detectado).")
                return True
            print(f"❌ Erro Real: {e}")
            return False
        finally:
            await browser.close()

if __name__ == '__main__':
    target_server = os.getenv("TARGET_SERVER", "SP")
    asyncio.run(restart_campaign(server=target_server))



































