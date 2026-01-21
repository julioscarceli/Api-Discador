# scripts/restart_campaign.py

import asyncio
import re
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login, get_fila_name, get_server_name
from config.settings import SAIDAS_VALOR

# --- Constantes de Seletores ---
SELETOR_BOTAO_FINALIZAR = 'button.btParar'
SELETOR_CONFIRMAR_FINALIZAR = 'button.swal2-confirm, button:has-text("Sim, pode finalizar!")'
SELETOR_INPUT_SAIDAS = '#saida'
SELETOR_BOTAO_SUBIR_MAILING = '#btCampanha1'
SELETOR_CARD_STATS = '.card-stats' 

async def get_current_campaign_name(page) -> str | None:
    """
    Extrai o nome da campanha com tolerância extrema e detecção de AJAX.
    """
    try:
        # 1. Aguarda a div principal que recebe o conteúdo AJAX carregar
        await page.wait_for_selector('#frmDiscador', state='attached', timeout=20000)
        
        # 2. Monitora a rede e aguarda o card de estatísticas
        print("[DEBUG] Aguardando o card de estatísticas aparecer na tela...")
        # Aumentamos para 45s para dar tempo ao banco de dados do discador
        await page.wait_for_selector(SELETOR_CARD_STATS, state='visible', timeout=45000)
        
        # 3. Localiza o bloco de texto onde está o nome da campanha
        stats_block = page.locator('.stats').filter(has_text="MAILING_DISCADOR")
        await stats_block.first.wait_for(state='visible', timeout=15000)
        
        text_content = await stats_block.first.inner_text()
        print(f"[DEBUG] Captura bruta: {text_content.strip()}")

        # 4. Extração via Regex (Busca o padrão que vimos no seu código fonte)
        match = re.search(r'MAILING_DISCADOR[^\n\r]+', text_content)
        if match:
            clean_name = match.group(0).replace('assignment:', '').strip()
            # Remove % ou infos de canais que podem vir na mesma string
            final_name = clean_name.split('  ')[0].strip()
            print(f"[DEBUG] Nome extraído: '{final_name}'")
            return final_name
        
        return None
    except Exception as e:
        print(f"[DEBUG] Falha técnica na extração: {e}")
        return None

async def navigate_to_send_page(page):
    """
    Realiza a navegação passo a passo garantindo que o clique em 'Enviar' ocorra.
    """
    # Navegação pelo menu lateral
    await page.get_by_role("link", name="send Discador Automático").click()
    await page.get_by_role("link", name="DA Preditivo").click(force=True)
    await page.wait_for_timeout(2000)
    
    # Clique em 'Enviar' - O ponto onde a tabela AJAX é disparada
    enviar_tab = page.get_by_text("Enviar")
    await enviar_tab.wait_for(state='visible', timeout=10000)
    await enviar_tab.click(force=True)

async def finalize_campaign_only(server: str):
    async with async_playwright() as p:
        context, page, browser = await create_context_and_login(p, server=server)
        if not context: return False
        server_name = get_server_name(server)

        try:
            print(f"[{server_name}] 1. Navegando para Limpeza UI...")
            await page.wait_for_timeout(5000)
            await navigate_to_send_page(page)

            # Força a finalização via JS direto (ignora o Timeout visual)
            botao = page.locator(SELETOR_BOTAO_FINALIZAR).first
            await botao.wait_for(state='attached', timeout=30000)
            await botao.evaluate("node => node.click()")

            confirmar = page.locator(SELETOR_CONFIRMAR_FINALIZAR).first
            await confirmar.wait_for(state='attached', timeout=10000)
            await confirmar.evaluate("node => node.click()")
            
            return True
        except Exception as e:
            print(f"[{server_name}] ❌ Falha na finalização API: {e}")
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
            print(f"[{server_name}] 1. Iniciando navegação...")
            await page.wait_for_timeout(5000) 
            await navigate_to_send_page(page)

            # Tenta extrair o nome. Se falhar, dá um reload e tenta de novo.
            current_campaign = await get_current_campaign_name(page)

            if not current_campaign:
                print(f"[{server_name}] 🔄 Tentativa 2: Recarregando página...")
                await page.reload(wait_until="networkidle")
                await page.wait_for_timeout(5000)
                # Tenta navegar novamente para a aba enviar após o F5
                await page.get_by_text("Enviar").click(force=True)
                current_campaign = await get_current_campaign_name(page)
                if not current_campaign: 
                    print(f"[{server_name}] ❌ Abortando: Dados não apareceram após F5.")
                    return False

            print(f"[{server_name}] ✅ Campanha ativa: {current_campaign}")

            # Parada da campanha atual
            botao = page.locator(SELETOR_BOTAO_FINALIZAR).first
            await botao.wait_for(state='attached', timeout=30000)
            await botao.evaluate("node => node.click()")
            
            confirmar = page.locator(SELETOR_CONFIRMAR_FINALIZAR).first
            await confirmar.wait_for(state='attached', timeout=15000)
            await confirmar.evaluate("node => node.click()")
            
            await page.wait_for_timeout(4000) 

            # Configuração dos dropdowns por data-id (visto no seu código fonte)
            print(f"[{server_name}] 3. Reconfigurando discagem...")
            
            # Dropdown Campanha
            await page.get_by_role("button", name="Escolha a opção").first.click()
            await page.wait_for_timeout(1000) 
            await page.locator('div.dropdown-menu.open').get_by_role("option", name=current_campaign).click() 

            # Dropdown Telefone
            await page.click('button[data-id="telefones"]')
            await page.wait_for_timeout(1000) 
            await page.locator('div.dropdown-menu.open').get_by_role("option", name=current_campaign).click() 

            # Dropdown Fila
            await page.click('button[data-id="fila"]')
            await page.wait_for_timeout(1000) 
            await page.locator('div.dropdown-menu.open').get_by_role("option", name=fila_name).click()

            await page.fill(SELETOR_INPUT_SAIDAS, SAIDAS_VALOR)
            await page.click(SELETOR_BOTAO_SUBIR_MAILING)
            
            print(f"[{server_name}] ✅ Restart Finalizado com Sucesso!")
            return True
        except Exception as e:
            print(f"[{server_name}] ❌ Erro Crítico no Restart: {e}")
            return False
        finally:
            if browser: await browser.close()

if __name__ == '__main__':
    asyncio.run(restart_campaign(server="MG"))
























