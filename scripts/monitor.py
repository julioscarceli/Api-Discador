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
SAIDAS_VALOR = "18"  # Configurado para 18 canais

URL_DA_SP = "https://186.194.50.149/azcall/pages/da.php"
URL_DA_MG = "http://186.194.50.155/azcall/pages/da.php"

# --- SELETORES ---
SELETOR_TAB_ENVIAR = 'a[data-toggle="tab"]:has-text("Enviar")'
SELETOR_BOTAO_FINALIZAR = 'button.btParar'
SELETOR_CONFIRMAR_FINALIZAR = 'button.swal2-confirm'
SELETOR_AGRESSIVIDADE_BOTAO = '#Agressive > div > label > span.toggle'

async def select_dropdown_option_forced(page, button_xpath, text_to_find, server_label, is_telefone=False):
    """Sincronização reforçada para garantir seleção em Headless."""
    try:
        btn = page.locator(button_xpath)
        await btn.wait_for(state="attached", timeout=20000)
        await btn.dispatch_event("click")
        await page.wait_for_timeout(2000)

        if is_telefone:
            # Seletor fixo para a segunda opção de telefone (padrão da operação)
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

async def restart_campaign(server: str):
    """Fluxo completo: Finaliza, Reconfigura com Agressividade e sobe com 18 canais."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        server_upper = server.upper()
        url_alvo = URL_DA_SP if server_upper == "SP" else URL_DA_MG
        fila_name = "DISCADOR_SP" if server_upper == "SP" else "DISCADOR_MG"

        try:
            print(f"[{server_upper}] Acessando URL Direta...")
            await page.goto(url_alvo, wait_until="commit", timeout=60000)

            # --- LOGIN ---
            user_input = page.locator('input[name="user"], input[placeholder*="Usuá"]').first
            if await user_input.is_visible(timeout=5000):
                await user_input.fill(DISCADOR_USER)
                await page.locator('input[type="password"]').fill(DISCADOR_PASS)
                await page.locator('button:has-text("ENTRAR")').click()
                await page.wait_for_load_state("domcontentloaded", timeout=30000)

            # --- ABA ENVIAR E IDENTIFICAÇÃO ---
            print(f"[{server_upper}] Sincronizando aba Enviar...")
            aba = page.locator(SELETOR_TAB_ENVIAR).first
            await aba.wait_for(state="attached", timeout=45000)
            await aba.dispatch_event("click")
            
            await page.wait_for_selector(".card-stats", state="visible", timeout=30000)
            stats_text = await page.locator(".card-stats").inner_text()
            match = re.search(r'MAILING_DISCADOR[^\s\n\r\-]+', stats_text)
            
            if not match: 
                print(f"[{server_upper}] ❌ Não foi possível identificar o mailing ativo.")
                return False
                
            current_campaign = match.group(0).strip()
            print(f"[{server_upper}] Campanha Detectada: {current_campaign}")

            # --- FINALIZAÇÃO DA CAMPANHA ATUAL ---
            print(f"[{server_upper}] Finalizando campanha atual...")
            btn_parar = page.locator(SELETOR_BOTAO_FINALIZAR).first
            if await btn_parar.is_visible():
                await btn_parar.dispatch_event("click")
                await page.locator(SELETOR_CONFIRMAR_FINALIZAR).first.dispatch_event("click")
                await page.wait_for_timeout(5000)

            # --- RECONFIGURAÇÃO ---
            print(f"[{server_upper}] Reconfigurando campos...")
            # Seleciona Mailing
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[2]/div/div/button', current_campaign, server_upper)
            # Seleciona Telefone
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[3]/div/div/button', current_campaign, server_upper, is_telefone=True)
            # Seleciona Fila
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[6]/div/div[1]/button', fila_name, server_upper)

            # --- ATIVAÇÃO DA AGRESSIVIDADE (REATIVADO) ---
            print(f"[{server_upper}] Ativando agressividade por agente...")
            await page.wait_for_selector(SELETOR_AGRESSIVIDADE_BOTAO)
            await page.click(SELETOR_AGRESSIVIDADE_BOTAO)
            
            # --- DISPARO FINAL ---
            print(f"[{server_upper}] Definindo {SAIDAS_VALOR} canais e iniciando...")
            await page.locator("#saida").fill(SAIDAS_VALOR)
            await page.wait_for_timeout(1000)
            await page.locator("#btCampanha1").dispatch_event("click")

            # Aguarda confirmação
            await page.wait_for_timeout(8000)
            print(f"[{server_upper}] ✅ RESTART CONCLUÍDO: 18 Canais + Agressividade Ativa.")
            return True

        except Exception as e:
            # Tratamento para erro de timeout fantasma após o clique de início
            if "Timeout" in str(e) and "btCampanha1" in str(e):
                print(f"[{server_upper}] ✅ Sucesso detectado (Timeout pós-disparo ignorado).")
                return True
            print(f"[{server_upper}] ❌ Erro durante o processo: {e}")
            return False
        finally:
            await browser.close()

if __name__ == '__main__':
    target_server = os.getenv("TARGET_SERVER", "SP")
    asyncio.run(restart_campaign(server=target_server))











