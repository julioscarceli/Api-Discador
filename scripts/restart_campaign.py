# scripts/restart_campaign.py

import asyncio
import re
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login, get_fila_name, get_server_name
from config.settings import SAIDAS_VALOR

# --- Constantes do Script (Seletores Validados) ---
SELETOR_BOTAO_FINALIZAR = 'button:has-text("Finalizar Campanha")'
SELETOR_CONFIRMAR_FINALIZAR = 'button:has-text("Sim, pode finalizar!")' # CORRIGIDO
SELETOR_INPUT_SAIDAS = '#saida'
SELETOR_BOTAO_SUBIR_MAILING = '#btCampanha1'
SELETOR_PAINEL_PENDENTES = 'text=Contatos pendentes'

# Seletores de Abertura de Dropdowns
SELETOR_BOTAO_FILA_ABRIR = 'xpath=//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[6]/div/div[1]/button'
SELETOR_BOTAO_TELEFONE_ABRIR = 'xpath=//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[3]/div/div[1]/button'

# NOVO SELETOR HIERÁRQUICO
SELETOR_LISTA_ABERTA_ITEM = 'div.dropdown-menu.open'

# MELHORIA: Seletor unificado para o botão vermelho em MG e SP usando a classe .btParar do HTML
SELETOR_FINALIZAR_ROBUSTO = 'button.btParar:has-text("Finalizar Campanha"), button.btParar, text=FINALIZAR CAMPANHA'


async def get_current_campaign_name(page) -> str | None:
    """
    Função para extrair o nome da campanha atualmente em execução, com tolerância de 20s.
    """
    try:
        # AUMENTO DE TIMEOUT: 20s para o painel de pendentes aparecer (Máxima tolerância)
        await page.wait_for_selector(SELETOR_PAINEL_PENDENTES, state='visible', timeout=20000) 
        
        # Busca flexível ignorando case
        campaign_elements = page.locator('text=/MAILING_DISCADOR/i')
        all_texts = await campaign_elements.all_inner_texts()

        for text in all_texts:
            clean_text = text.strip()
            # Limpeza baseada no print: remove quebras de linha e lixo de ícones
            nome_puro = clean_text.split('\n')[0].replace('assignment:', '').strip()
            if "MAILING_DISCADOR" in nome_puro.upper():
                return nome_puro
        return None
    except Exception:
        return None


# --- FUNÇÃO ISOLADA PARA LIMPEZA (CHAMADA PELA API E DAILY WORKER) ---
async def finalize_campaign_only(server: str):
    """Navega até a página de envio e executa apenas a finalização da campanha atual."""
    async with async_playwright() as p:
        context, page, browser = await create_context_and_login(p, server=server)

        if not context:
            return False

        server_name = get_server_name(server)

        try:
            print(f"[{server_name}] 1. Navegando para Finalização de Campanha via API...")
            await page.wait_for_timeout(5000)

            await page.get_by_role("link", name="send Discador Automático").click()
            await page.wait_for_timeout(500)
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            await page.wait_for_timeout(1000)
            await page.get_by_text("Enviar").click(force=True)

            print(f"[{server_name}] 2. Finalizando Campanha atual via UI...")

            # Localiza, rola e clica forçado no botão (usando a classe .btParar e Regex)
            botao = page.locator(SELETOR_FINALIZAR_ROBUSTO).first
            await botao.wait_for(state='visible', timeout=30000)
            await botao.scroll_into_view_if_needed()
            await botao.click(force=True)

            await page.wait_for_selector(SELETOR_CONFIRMAR_FINALIZAR, state='visible', timeout=15000)
            await page.click(SELETOR_CONFIRMAR_FINALIZAR, force=True)

            print(f"[{server_name}] ✅ Campanha antiga finalizada com sucesso.")
            await page.wait_for_timeout(2000)
            return True

        except Exception as e:
            print(f"[{server_name}] ❌ Erro durante a FINALIZAÇÃO da campanha: {e}")
            return False

        finally:
            if browser:
                await browser.close()

async def restart_campaign(server: str): 
    async with async_playwright() as p:
        context, page, browser = await create_context_and_login(p, server=server)

        if not context:
            return False

        server_name = get_server_name(server)
        fila_name = get_fila_name(server)

        try:
            print(f"[{server_name}] 1. Navegando para Envio de Campanhas e extraindo nome da campanha...")
            await page.wait_for_timeout(5000) 

            await page.get_by_role("link", name="send Discador Automático").click()
            await page.wait_for_timeout(500) 
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            await page.wait_for_timeout(1000)
            await page.get_by_text("Enviar").click(force=True)

            current_campaign = await get_current_campaign_name(page)

            if not current_campaign:
                print(f"[{server_name}] ⚠️ Alerta: Não foi possível obter o nome da campanha. Abortando restart.")
                return False

            print(f"[{server_name}] ✅ Campanha atual identificada: {current_campaign}")

            print(f"[{server_name}] 2. Finalizando Campanha atual...")
            
            # Localização robusta do botão baseada no HTML e Classe técnica fornecida
            botao = page.locator(SELETOR_FINALIZAR_ROBUSTO).first
            await botao.wait_for(state='visible', timeout=30000)
            await botao.scroll_into_view_if_needed()
            await botao.click(force=True)
            
            await page.wait_for_selector(SELETOR_CONFIRMAR_FINALIZAR, state='visible', timeout=15000)
            await page.click(SELETOR_CONFIRMAR_FINALIZAR, force=True) 
            
            await page.wait_for_timeout(3000) 

            print(f"[{server_name}] 3. Reconfigurando e disparando o mailing...")

            await page.get_by_role("button", name="Escolha a opção").first.click()
            await page.wait_for_timeout(800) 
            
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=current_campaign).wait_for(state='visible', timeout=10000) 
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=current_campaign).click(timeout=20000) 

            await page.click(SELETOR_BOTAO_TELEFONE_ABRIR)
            await page.wait_for_timeout(800) 
            
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=current_campaign).wait_for(state='visible', timeout=10000)
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=current_campaign).click(timeout=20000) 

            await page.click(SELETOR_BOTAO_FILA_ABRIR)
            await page.wait_for_timeout(800) 
            
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=fila_name).wait_for(state='visible', timeout=10000)
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=fila_name).click(timeout=20000)

            await page.fill(SELETOR_INPUT_SAIDAS, SAIDAS_VALOR)
            await page.click(SELETOR_BOTAO_SUBIR_MAILING)
            
            await page.wait_for_timeout(2000) 

            print(f"[{server_name}] ✅ Campanhas reconfigurada e subida com sucesso!")
            return True

        except Exception as e:
            print(f"[{server_name}] ❌ Erro durante a automação do restart: {e}")
            return False

        finally:
            if browser: 
                await browser.close()


if __name__ == '__main__':
    import asyncio
    asyncio.run(restart_campaign(server="MG"))



















