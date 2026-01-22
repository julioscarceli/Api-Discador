# scripts/restart_campaign.py

import asyncio
import re
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login, get_fila_name, get_server_name
from config.settings import SAIDAS_VALOR

# --- Constantes de Seletores (Validados via seu HTML) ---
SELETOR_TAB_ENVIAR = 'a[data-toggle="tab"]:has-text("Enviar")'
SELETOR_BOTAO_FINALIZAR = 'button.btParar'
SELETOR_CONFIRMAR_FINALIZAR = 'button.swal2-confirm, button:has-text("Sim, pode finalizar!")'
SELETOR_INPUT_SAIDAS = '#saida'
SELETOR_BOTAO_SUBIR_MAILING = '#btCampanha1'
SELETOR_CARD_STATS = '.card-stats' 

async def get_current_campaign_name(page) -> str | None:
    """Extrai o nome da campanha aguardando a renderização dinâmica."""
    try:
        # Aguarda a estabilização da rede (AJAX concluído)
        await page.wait_for_load_state("networkidle", timeout=30000)
        await page.wait_for_selector(SELETOR_CARD_STATS, state='attached', timeout=45000)
        
        # Filtra o bloco stats que contém o texto da campanha
        locator = page.locator('.stats').filter(has_text="MAILING_DISCADOR")
        await locator.first.wait_for(state='visible', timeout=15000)
        
        text_content = await locator.first.inner_text()
        
        # Regex para isolar o nome real do mailing
        match = re.search(r'MAILING_DISCADOR[^\n\r]+', text_content)
        if match:
            clean_name = match.group(0).replace('assignment:', '').strip()
            return clean_name.split('  ')[0].strip()
        return None
    except Exception as e:
        print(f"[DEBUG] Falha na extração de nome: {e}")
        return None

async def safe_click_enviar(page):
    """Executa o clique na aba Enviar ignorando obstruções visuais."""
    # Localiza o elemento
    enviar_element = page.locator(SELETOR_TAB_ENVIAR).first
    await enviar_element.wait_for(state='attached', timeout=20000)
    
    # SOLUÇÃO PARA O ERRO: Dispara o clique via JS para ignorar a Navbar que está na frente
    print("[DEBUG] Disparando clique forçado na aba Enviar...")
    await enviar_element.dispatch_event("click")

async def finalize_campaign_only(server: str):
    """Navega até a página de envio e executa apenas a finalização da campanha atual."""
    async with async_playwright() as p:
        context, page, browser = await create_context_and_login(p, server=server)
        if not context: return False
        server_name = get_server_name(server)

        try:
            print(f"[{server_name}] 1. Navegando para Limpeza UI...")
            await page.wait_for_timeout(5000)
            
            # Navegação via menu lateral
            await page.get_by_role("link", name="send Discador Automático").click()
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            await asyncio.sleep(2)
            
            # Clique seguro na aba 'Enviar'
            await safe_click_enviar(page)

            print(f"[{server_name}] 2. Finalizando Campanha atual via UI...")
            # Força a finalização via JS direto para ignorar obstruções
            botao_parar = page.locator(SELETOR_BOTAO_FINALIZAR).first
            await botao_parar.wait_for(state='attached', timeout=30000)
            await botao_parar.dispatch_event("click")
            
            confirmar = page.locator(SELETOR_CONFIRMAR_FINALIZAR).first
            await confirmar.wait_for(state='attached', timeout=10000)
            await confirmar.dispatch_event("click")
            
            print(f"[{server_name}] ✅ Campanha antiga finalizada com sucesso.")
            await page.wait_for_timeout(2000)
            return True
        except Exception as e:
            print(f"[{server_name}] ❌ Erro durante a FINALIZAÇÃO da campanha: {e}")
            return False
        finally:
            if browser: await browser.close()

async def restart_campaign(server: str): 
    async with async_playwright() as p:
        context, page, browser = await create_context_and_login(p, server=server)
        if not context: return False

        server_name = get_server_name(server)
        fila_name = get_fila_name(server)

        try:
            print(f"[{server_name}] 1. Navegando para aba de Envio...")
            await page.wait_for_timeout(5000) 
            
            # Navegação via menu lateral
            await page.get_by_role("link", name="send Discador Automático").click()
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            await asyncio.sleep(2)
            
            # Clique seguro na aba 'Enviar'
            await safe_click_enviar(page)

            # Extração do nome
            current_campaign = await get_current_campaign_name(page)

            if not current_campaign:
                print(f"[{server_name}] ⚠️ Alerta: Dados não carregaram. Tentando F5...")
                await page.reload()
                await page.wait_for_timeout(5000)
                await safe_click_enviar(page)
                current_campaign = await get_current_campaign_name(page)
                if not current_campaign: return False

            print(f"[{server_name}] ✅ Campanha identificada: {current_campaign}")

            # Parada da campanha atual via JS para evitar interceptação
            botao_parar = page.locator(SELETOR_BOTAO_FINALIZAR).first
            await botao_parar.wait_for(state='attached', timeout=30000)
            await botao_parar.dispatch_event("click")
            
            confirmar = page.locator(SELETOR_CONFIRMAR_FINALIZAR).first
            await confirmar.wait_for(state='attached', timeout=10000)
            await confirmar.dispatch_event("click")
            
            await page.wait_for_timeout(5000) 

# ----------------------------------------------------
            # ETAPA 3: RECONFIGURAÇÃO E DISPARO (AÇÕES ROBUSTAS)
            # ----------------------------------------------------
            print(f"[{server_name}] 3. Reconfigurando discagem...")

            # --- AÇÃO A: Selecionar a CAMPANHA (2ª Coluna) ---
            # Localiza o botão pelo XPath específico da estrutura que você enviou
            btn_campanha = page.locator('//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[2]/div/div/button')
            await btn_campanha.wait_for(state='visible', timeout=10000)
            await btn_campanha.click()
            await page.wait_for_timeout(1000) 

            # Clica na opção que contém o nome da campanha (MAILING_DISCADOR...)
            # Usamos .first para evitar o erro de duplicidade (strict mode)
            await page.locator('div.dropdown-menu.open ul li a').filter(has_text=current_campaign).first.click()
            print(f"[{server_name}] - Campanha '{current_campaign}' selecionada.")

            # --- AÇÃO B: Selecionar o TELEFONE (3ª Coluna) ---
            btn_telefone = page.locator('//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[3]/div/div/button')
            await btn_telefone.wait_for(state='visible', timeout=10000)
            await btn_telefone.click()
            await page.wait_for_timeout(1000)

            # Seleciona a opção de telefone correspondente
            await page.locator('div.dropdown-menu.open ul li a').filter(has_text=current_campaign).first.click()
            print(f"[{server_name}] - Telefone selecionado.")

            # --- AÇÃO C: Selecionar a FILA DE ATENDIMENTO (6ª Coluna) ---
            btn_fila = page.locator('//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[6]/div/div[1]/button')
            await btn_fila.wait_for(state='visible', timeout=10000)
            await btn_fila.click()
            await page.wait_for_timeout(1000)

            # Seleciona a fila conforme a região (DISCADOR_SP ou DISCADOR_MG)
            await page.locator('div.dropdown-menu.open ul li a').filter(has_text=fila_name).first.click()
            print(f"[{server_name}] - Fila '{fila_name}' selecionada.")

            # --- FINALIZAÇÃO: Saídas e Botão Subir ---
            # Preenche o campo Saídas (#saida)
            input_saidas = page.locator(SELETOR_INPUT_SAIDAS)
            await input_saidas.wait_for(state='visible')
            await input_saidas.fill(str(SAIDAS_VALOR))

            # Clica no botão de aviãozinho para disparar (#btCampanha1)
            btn_subir = page.locator(SELETOR_BOTAO_SUBIR_MAILING)
            await btn_subir.wait_for(state='visible')
            await btn_subir.click()
            
            await page.wait_for_timeout(3000)
            print(f"[{server_name}] ✅ RESTART EXECUTADO COM SUCESSO!")
            return True

        except Exception as e:
            print(f"[{server_name}] ❌ Erro Crítico no Restart: {e}")
            return False
        finally:
            if browser: 
                await browser.close()

if __name__ == '__main__':
    # Teste rápido manual
    asyncio.run(restart_campaign(server="MG"))




























