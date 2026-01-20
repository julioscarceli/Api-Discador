# scripts/restart_campaign.py

import asyncio
import re
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login, get_fila_name, get_server_name
from config.settings import SAIDAS_VALOR

# --- Constantes do Script (Seletores Extraídos do Código Fonte) ---
SELETOR_BOTAO_FINALIZAR = 'button.btParar'
SELETOR_CONFIRMAR_FINALIZAR = 'button:has-text("Sim, pode finalizar!"), .swal2-confirm'
SELETOR_INPUT_SAIDAS = '#saida'
SELETOR_BOTAO_SUBIR_MAILING = '#btCampanha1'
SELETOR_TABELA_CONTAINER = '#Tabela' # Container que recebe o carregamento AJAX

# Seletor para os itens da lista aberta nos dropdowns (Bootstrap Select)
SELETOR_LISTA_ABERTA_ITEM = 'div.dropdown-menu.open'


async def get_current_campaign_name(page) -> str | None:
    """
    Extrai o nome da campanha esperando o carregamento AJAX do card.
    """
    try:
        # 1. AGUARDA O AJAX: Espera até que o card com o nome apareça dentro da tabela
        print("[DEBUG] Aguardando carregamento dos dados da campanha...")
        await page.wait_for_selector('.card-stats .stats', state='visible', timeout=30000)
        
        # 2. Localiza o bloco de estatísticas que contém o ícone 'assignment' (Campanha)
        # O locator busca o elemento pai que contém o texto da campanha
        stats_block = page.locator('.card-footer .stats').filter(has_text="MAILING_DISCADOR")
        
        all_text = await stats_block.first.inner_text()
        print(f"[DEBUG] Texto bruto encontrado no card: {all_text}")

        # 3. Limpeza rigorosa via Regex (Pega exatamente a linha do mailing)
        match = re.search(r'MAILING_DISCADOR[^\n\r]+', all_text)
        if match:
            clean_name = match.group(0).strip()
            # Remove sufixos de % ou espaços duplos
            clean_name = clean_name.split('  ')[0].strip()
            print(f"[DEBUG] Nome Identificado: '{clean_name}'")
            return clean_name
        
        return None
    except Exception as e:
        print(f"[DEBUG] Erro ao carregar nome via AJAX: {e}")
        return None


async def finalize_campaign_only(server: str):
    """Função usada pela API para limpar o terreno antes do upload."""
    async with async_playwright() as p:
        context, page, browser = await create_context_and_login(p, server=server)
        if not context: return False
        server_name = get_server_name(server)

        try:
            print(f"[{server_name}] 1. Navegando para Limpeza UI...")
            await page.wait_for_timeout(5000)
            await page.get_by_role("link", name="send Discador Automático").click()
            await page.wait_for_timeout(500)
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            await page.wait_for_timeout(1000)
            await page.get_by_text("Enviar").click(force=True)

            # Aguarda o botão de parar carregar na tabela dinâmica
            await page.wait_for_selector(SELETOR_BOTAO_FINALIZAR, state='visible', timeout=30000)

            print(f"[{server_name}] 2. Executando clique em Finalizar...")
            botao = page.locator(SELETOR_BOTAO_FINALIZAR).first
            await botao.scroll_into_view_if_needed()
            await botao.click(force=True)

            # Confirmação no SweetAlert (vimos no seu JS que ele usa swal)
            await page.wait_for_selector(SELETOR_CONFIRMAR_FINALIZAR, state='visible', timeout=15000)
            await page.click(SELETOR_CONFIRMAR_FINALIZAR, force=True)

            print(f"[{server_name}] ✅ Campanha antiga encerrada.")
            await page.wait_for_timeout(3000)
            return True
        except Exception as e:
            print(f"[{server_name}] ❌ Falha na limpeza: {e}")
            return False
        finally:
            if browser: await browser.close()

async def restart_campaign(server: str): 
    """Função usada pelo Monitoramento Automático."""
    async with async_playwright() as p:
        context, page, browser = await create_context_and_login(p, server=server)
        if not context: return False

        server_name = get_server_name(server)
        fila_name = get_fila_name(server)

        try:
            print(f"[{server_name}] 1. Navegando e aguardando sincronia AJAX...")
            await page.wait_for_timeout(5000) 
            await page.get_by_role("link", name="send Discador Automático").click()
            await page.wait_for_timeout(500) 
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            await page.wait_for_timeout(1000)
            await page.get_by_text("Enviar").click(force=True)

            # Extração que agora sabe esperar o conteúdo aparecer
            current_campaign = await get_current_campaign_name(page)

            if not current_campaign:
                print(f"[{server_name}] ⚠️ Alerta: Campanha não carregou na tela. Abortando.")
                return False

            print(f"[{server_name}] ✅ Campanha ativa detectada: {current_campaign}")

            print(f"[{server_name}] 2. Finalizando Campanha...")
            botao = page.locator(SELETOR_BOTAO_FINALIZAR).first
            await botao.wait_for(state='visible', timeout=30000)
            await botao.scroll_into_view_if_needed()
            await botao.click(force=True)
            
            await page.wait_for_selector(SELETOR_CONFIRMAR_FINALIZAR, state='visible', timeout=15000)
            await page.click(SELETOR_CONFIRMAR_FINALIZAR, force=True) 
            await page.wait_for_timeout(3000) 

            print(f"[{server_name}] 3. Reconfigurando Dropdowns...")
            await page.get_by_role("button", name="Escolha a opção").first.click()
            await page.wait_for_timeout(800) 
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=current_campaign).click(timeout=20000) 

            await page.click('xpath=//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[3]/div/div[1]/button')
            await page.wait_for_timeout(800) 
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=current_campaign).click(timeout=20000) 

            await page.click('xpath=//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[6]/div/div[1]/button')
            await page.wait_for_timeout(800) 
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=fila_name).click(timeout=20000)

            await page.fill(SELETOR_INPUT_SAIDAS, SAIDAS_VALOR)
            await page.click(SELETOR_BOTAO_SUBIR_MAILING)
            await page.wait_for_timeout(2000) 

            print(f"[{server_name}] ✅ Restart Completo!")
            return True
        except Exception as e:
            print(f"[{server_name}] ❌ Erro no restart: {e}")
            return False
        finally:
            if browser: await browser.close()

if __name__ == '__main__':
    asyncio.run(restart_campaign(server="MG"))




















