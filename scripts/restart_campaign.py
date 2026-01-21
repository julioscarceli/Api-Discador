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

            # Configuração dos Dropdowns via data-id
            print(f"[{server_name}] 3. Reconfigurando discagem...")
            
            # Seleciona Campanha
            await page.get_by_role("button", name="Escolha a opção").first.click()
            await page.locator('div.dropdown-menu.open').get_by_role("option", name=current_campaign).click() 

            # Seleciona Telefone
            await page.click('button[data-id="telefones"]')
            await page.locator('div.dropdown-menu.open').get_by_role("option", name=current_campaign).click() 

            # Seleciona Fila
            await page.click('button[data-id="fila"]')
            await page.locator('div.dropdown-menu.open').get_by_role("option", name=fila_name).click()

            # Disparo Final
            await page.fill(SELETOR_INPUT_SAIDAS, SAIDAS_VALOR)
            await page.click(SELETOR_BOTAO_SUBIR_MAILING)
            
            print(f"[{server_name}] ✅ RESTART EXECUTADO!")
            return True
        except Exception as e:
            print(f"[{server_name}] ❌ Erro Crítico no Restart: {e}")
            return False
        finally:
            if browser: await browser.close()

if __name__ == '__main__':
    asyncio.run(restart_campaign(server="MG"))



























