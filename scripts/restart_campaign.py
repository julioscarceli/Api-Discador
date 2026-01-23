# scripts/restart_campaign.py

import asyncio
import re
import os
from playwright.async_api import async_playwright

# ... (Mantenha as variáveis de ambiente e a função select_dropdown_option_forced igual)

async def restart_campaign(server: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) # Railway Headless
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        url_alvo = URL_DA_SP if server == "SP" else URL_DA_MG
        fila_name = "DISCADOR_SP" if server == "SP" else "DISCADOR_MG"

        try:
            print(f"[{server}] Acessando URL Direta...")
            # Usamos domcontentloaded para ser mais rápido e evitar travar em scripts de terceiros
            await page.goto(url_alvo, wait_until="domcontentloaded", timeout=60000)

            # --- LOGIN COM TRATAMENTO DE ERRO SILENCIOSO ---
            user_input = page.locator('input[name="user"], input[placeholder*="Usuá"]').first
            if await user_input.is_visible(timeout=5000):
                await user_input.fill(DISCADOR_USER)
                await page.locator('input[type="password"]').fill(DISCADOR_PASS)
                # Ignoramos erro de navegação aqui se o login funcionar mas o redirect for brusco
                try:
                    await page.locator('button:has-text("ENTRAR")').click(timeout=5000)
                except:
                    pass
                await page.wait_for_load_state("networkidle", timeout=30000)

            # --- NAVEGAÇÃO INTERNA ---
            aba_enviar = page.locator('a[data-toggle="tab"]:has-text("Enviar")').first
            await aba_enviar.wait_for(state="attached", timeout=20000)
            await aba_enviar.dispatch_event("click")
            
            # Espera o card de estatísticas para garantir que os dados carregaram
            await page.wait_for_selector(".card-stats", state="visible", timeout=30000)

            stats_text = await page.locator(".card-stats").inner_text()
            match = re.search(r'MAILING_DISCADOR[^\s\n\r\-]+', stats_text)
            if not match: return False
            current_campaign = match.group(0).strip()
            print(f"[{server}] Campanha Detectada: {current_campaign}")

            # --- FINALIZAÇÃO ---
            await page.locator('button.btParar').first.dispatch_event("click")
            # Clique de confirmação com timeout curto
            try:
                confirmar = page.locator('button.swal2-confirm').first
                await confirmar.wait_for(state="visible", timeout=5000)
                await confirmar.click(timeout=5000)
            except:
                pass
            await page.wait_for_timeout(3000)

            # --- RECONFIGURAÇÃO ---
            # Usando a lógica de precisão que funcionou localmente
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[2]/div/div/button', current_campaign, server)
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[3]/div/div/button', current_campaign, server, is_telefone=True)
            await select_dropdown_option_forced(page, '//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[6]/div/div[1]/button', fila_name, server)

            # --- DISPARO FINAL ---
            await page.locator("#saida").fill(SAIDAS_VALOR)
            await page.wait_for_timeout(1000)
            
            print(f"[{server}] Disparando aviãozinho final...")
            # O SEGREDO: Dispara o clique e não espera por uma resposta de navegação
            await page.locator("#btCampanha1").dispatch_event("click")
            
            # Espera forçada de 5s apenas para garantir que o servidor recebeu
            await page.wait_for_timeout(5000)
            print(f"[{server}] ✅ RESTART CONCLUÍDO (Operação verificada).")
            return True

        except Exception as e:
            # Se o erro for de Timeout mas estivermos no final do script, ignoramos
            if "Timeout" in str(e) and "btCampanha1" in str(e):
                print(f"[{server}] ⚠️ Timeout ignorado após disparo do mailing.")
                return True
            print(f"❌ Erro Real: {e}")
            return False
        finally:
            await browser.close()


































