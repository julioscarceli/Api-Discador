# scripts/restart_campaign.py

import asyncio
import re
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login, get_fila_name, get_server_name
from config.settings import SAIDAS_VALOR

# --- Constantes de Seletores (Baseadas no seu Código Fonte) ---
SELETOR_BOTAO_FINALIZAR = 'button.btParar'
SELETOR_CONFIRMAR_FINALIZAR = 'button:has-text("Sim, pode finalizar!"), .swal2-confirm'
SELETOR_INPUT_SAIDAS = '#saida'
SELETOR_BOTAO_SUBIR_MAILING = '#btCampanha1'
SELETOR_CARD_STATS = '.card-stats' 

async def get_current_campaign_name(page) -> str | None:
    """
    Extrai o nome da campanha esperando a estabilização do AJAX.
    """
    try:
        # Espera a rede parar de trafegar dados (carregamento AJAX concluído)
        await page.wait_for_load_state("networkidle", timeout=20000)
        
        # Localiza o card de estatísticas
        locator = page.locator('.stats').filter(has_text="MAILING_DISCADOR")
        await locator.first.wait_for(state='visible', timeout=20000)
        
        text_content = await locator.first.inner_text()
        
        # Busca o padrão MAILING_DISCADOR no texto capturado
        match = re.search(r'MAILING_DISCADOR[^\n\r]+', text_content)
        if match:
            clean_name = match.group(0).replace('assignment:', '').strip()
            # Pega apenas a primeira parte antes de espaços duplos ou quebras
            return clean_name.split('  ')[0].strip()
        
        return None
    except Exception as e:
        print(f"[DEBUG] Erro ao extrair nome: {e}")
        return None

async def finalize_campaign_only(server: str):
    """Executa apenas a finalização (Limpeza UI via API)."""
    async with async_playwright() as p:
        context, page, browser = await create_context_and_login(p, server=server)
        if not context: return False
        server_name = get_server_name(server)

        try:
            print(f"[{server_name}] 1. Navegando para Envio (API)...")
            await page.wait_for_timeout(3000)
            await page.get_by_role("link", name="send Discador Automático").click()
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            await asyncio.sleep(1)
            await page.get_by_text("Enviar").click(force=True)

            print(f"[{server_name}] 2. Finalizando Campanha (Clique via Script)...")
            # Espera o botão estar no HTML e clica via evaluate para ignorar bloqueios visuais
            botao = page.locator(SELETOR_BOTAO_FINALIZAR).first
            await botao.wait_for(state='attached', timeout=30000)
            await botao.evaluate("node => node.click()")

            # Confirmação
            confirmar = page.locator(SELETOR_CONFIRMAR_FINALIZAR).first
            await confirmar.wait_for(state='attached', timeout=10000)
            await confirmar.evaluate("node => node.click()")
            
            print(f"[{server_name}] ✅ Finalização concluída via API.")
            return True
        except Exception as e:
            print(f"[{server_name}] ❌ Falha na finalização: {e}")
            return False
        finally:
            if browser: await browser.close()

async def restart_campaign(server: str): 
    """Executa o ciclo completo de Restart (Monitor)."""
    async with async_playwright() as p:
        context, page, browser = await create_context_and_login(p, server=server)
        if not context: return False

        server_name = get_server_name(server)
        fila_name = get_fila_name(server)

        try:
            print(f"[{server_name}] 1. Navegando e extraindo dados...")
            await page.wait_for_timeout(3000) 
            await page.get_by_role("link", name="send Discador Automático").click()
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            await asyncio.sleep(1)
            await page.get_by_text("Enviar").click(force=True)

            current_campaign = await get_current_campaign_name(page)
            if not current_campaign:
                print(f"[{server_name}] ⚠️ Alerta: Campanha não carregou. Tentando F5...")
                await page.reload()
                current_campaign = await get_current_campaign_name(page)
                if not current_campaign: return False

            print(f"[{server_name}] ✅ Campanha: {current_campaign}. Finalizando...")
            
            # Clique de finalização robusto
            botao = page.locator(SELETOR_BOTAO_FINALIZAR).first
            await botao.wait_for(state='attached', timeout=20000)
            await botao.evaluate("node => node.click()")
            
            confirmar = page.locator(SELETOR_CONFIRMAR_FINALIZAR).first
            await confirmar.wait_for(state='attached', timeout=10000)
            await confirmar.evaluate("node => node.click()")
            
            await page.wait_for_timeout(3000) 

            print(f"[{server_name}] 3. Reconfigurando Dropdowns...")
            # Dropdown Campanha
            await page.get_by_role("button", name="Escolha a opção").first.click()
            await page.wait_for_timeout(800) 
            await page.locator('div.dropdown-menu.open').get_by_role("option", name=current_campaign).click() 

            # Dropdown Telefone (Usando data-id do seu HTML)
            await page.click('button[data-id="telefones"]')
            await page.wait_for_timeout(800) 
            await page.locator('div.dropdown-menu.open').get_by_role("option", name=current_campaign).click() 

            # Dropdown Fila
            await page.click('button[data-id="fila"]')
            await page.wait_for_timeout(800) 
            await page.locator('div.dropdown-menu.open').get_by_role("option", name=fila_name).click()

            await page.fill(SELETOR_INPUT_SAIDAS, SAIDAS_VALOR)
            await page.click(SELETOR_BOTAO_SUBIR_MAILING)
            
            print(f"[{server_name}] ✅ Restart OK!")
            return True
        except Exception as e:
            print(f"[{server_name}] ❌ Erro: {e}")
            return False
        finally:
            if browser: await browser.close()

if __name__ == '__main__':
    # Teste rápido manual
    asyncio.run(restart_campaign(server="MG"))






















