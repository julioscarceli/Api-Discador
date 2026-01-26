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

# --- SELETORES ---
SELETOR_TAB_ENVIAR = 'a[data-toggle="tab"]:has-text("Enviar")'
SELETOR_BOTAO_FINALIZAR = 'button.btParar'
SELETOR_CONFIRMAR_FINALIZAR = 'button.swal2-confirm'

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
    """Finaliza a campanha ativa com verificação de estado para garantir a limpeza."""
    server_name = server.upper()
    async with async_playwright() as p:
        # 1. Login com a nossa função otimizada
        context, page, browser = await create_context_and_login(p, server=server)
        if not context: 
            print(f"[{server_name}] ❌ Falha no login para finalização.")
            return False
            
        try:
            print(f"[{server_name}] ⏳ Acedendo à aba de controlo...")
            
            # 2. Ir para a aba Enviar (Onde estão os controlos)
            # Esperamos que o seletor esteja não apenas visível, mas estável
            aba_enviar = page.locator(SELETOR_TAB_ENVIAR).first
            await aba_enviar.wait_for(state="visible", timeout=15000)
            await aba_enviar.click(force=True)
            
            # Pequena pausa para a UI carregar os botões da aba
            await page.wait_for_timeout(2000)

            # 3. Clicar em Finalizar
            btn_finalizar = page.locator(SELETOR_BOTAO_FINALIZAR).first
            if await btn_finalizar.is_visible():
                print(f"[{server_name}] 🖱️ Clicando no botão Finalizar...")
                await btn_finalizar.click(force=True)
                
                # 4. Confirmar no Modal (O ponto onde costuma falhar)
                btn_confirmar = page.locator(SELETOR_CONFIRMAR_FINALIZAR).first
                # Esperamos o modal de confirmação aparecer
                await btn_confirmar.wait_for(state="visible", timeout=7000)
                
                print(f"[{server_name}] ⚠️ Confirmando finalização...")
                await btn_confirmar.click(force=True)
                
                # --- VERIFICAÇÃO DE SUCESSO ---
                # Em vez de apenas esperar 2s, esperamos o botão de confirmar desaparecer
                # Isso indica que o servidor respondeu e a UI fechou o modal.
                await btn_confirmar.wait_for(state="hidden", timeout=10000)
                
                # Espera extra de segurança para o DB do discador processar
                await page.wait_for_timeout(3000)
                print(f"[{server_name}] ✅ Campanha finalizada e confirmada.")
            else:
                print(f"[{server_name}] ℹ️ Botão finalizar não visível (Campanha já pode estar parada).")

            return True

        except Exception as e:
            print(f"[{server_name}] ❌ Erro Crítico na Finalização: {str(e)}")
            # Tira um print se falhar (útil para debug no Railway se tiveres volume mapeado)
            # await page.screenshot(path=f"erro_finalizar_{server_name}.png")
            return False
        finally:
            await browser.close()

async def restart_campaign(server: str):
    """Fluxo ultra-resiliente para eliminar o Timeout do Railway."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        url_alvo = URL_DA_SP if server == "SP" else URL_DA_MG
        fila_name = "DISCADOR_SP" if server == "SP" else "DISCADOR_MG"

        try:
            print(f"[{server}] Acessando URL Direta...")
            # Mudamos para 'commit' para agir assim que o servidor responder
            await page.goto(url_alvo, wait_until="commit", timeout=60000)

            # --- LOGIN RÁPIDO ---
            user_input = page.locator('input[name="user"], input[placeholder*="Usuá"]').first
            if await user_input.is_visible(timeout=5000):
                await user_input.fill(DISCADOR_USER)
                await page.locator('input[type="password"]').fill(DISCADOR_PASS)
                await page.locator('button:has-text("ENTRAR")').click()
                # Espera apenas o carregamento do DOM inicial
                await page.wait_for_load_state("domcontentloaded", timeout=30000)

            # --- MELHORIA: CORREÇÃO DE ROTA ANTI-TIMEOUT ---
            # Se o login te jogou para rs.php ou ch.php, força a volta para da.php
            if "da.php" not in page.url:
                print(f"[{server}] Redirecionado para {page.url}. Forçando retorno para DA...")
                await page.goto(url_alvo, wait_until="domcontentloaded", timeout=45000)

            # --- ABA ENVIAR ---
            print(f"[{server}] Sincronizando aba Enviar...")
            aba = page.locator(SELETOR_TAB_ENVIAR).first
            # Aumentamos o timeout para 45s para lidar com a latência do Railway
            await aba.wait_for(state="attached", timeout=45000)
            await aba.dispatch_event("click")
            
            # BLOQUEIO DE SEGURANÇA: Espera o elemento de stats que confirma o carregamento da aba
            await page.wait_for_selector(".card-stats", state="visible", timeout=30000)
            
            stats_text = await page.locator(".card-stats").inner_text()
            match = re.search(r'MAILING_DISCADOR[^\s\n\r\-]+', stats_text)
            if not match: return False
            current_campaign = match.group(0).strip()
            print(f"[{server}] Campanha Detectada: {current_campaign}")

            # --- FINALIZAÇÃO ---
            await page.locator(SELETOR_BOTAO_FINALIZAR).first.dispatch_event("click")
            await page.locator(SELETOR_CONFIRMAR_FINALIZAR).first.dispatch_event("click")
            await page.wait_for_timeout(5000)

            # --- RECONFIGURAÇÃO (Correção Telefone) ---
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[2]/div/div/button', current_campaign, server)
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[3]/div/div/button', current_campaign, server, is_telefone=True)
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[6]/div/div[1]/button', fila_name, server)

            # --- DISPARO ---
            await page.locator("#saida").fill(SAIDAS_VALOR)
            await page.wait_for_timeout(1000)
            await page.locator("#btCampanha1").dispatch_event("click")

            # Espera de confirmação final
            await page.wait_for_timeout(8000)
            print(f"[{server}] ✅ RESTART CONCLUÍDO COM SUCESSO.")
            return True

        except Exception as e:
            # Tratamento para redirecionamentos pós-clique que geram timeouts falsos
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








































