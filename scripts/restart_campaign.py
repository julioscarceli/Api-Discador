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
# Seletor do card que contém as informações que vimos no seu print
SELETOR_STATS_CAMPANHA = '.card-stats .stats' 

async def get_current_campaign_name(page) -> str | None:
    """
    Extrai o nome da campanha com múltiplas tentativas de leitura.
    """
    try:
        # Aguarda a rede ficar ociosa (AJAX concluído)
        await page.wait_for_load_state("networkidle", timeout=20000)
        
        # Tenta localizar o bloco de estatísticas onde está o ícone 'assignment'
        locator = page.locator('.stats').filter(has_text="MAILING_DISCADOR")
        
        # Espera o texto aparecer com 30s de timeout
        await locator.first.wait_for(state='visible', timeout=30000)
        
        text_content = await locator.first.inner_text()
        
        # Regex para capturar o nome do mailing na primeira linha
        match = re.search(r'MAILING_DISCADOR[^\n\r]+', text_content)
        if match:
            clean_name = match.group(0).replace('assignment:', '').strip()
            # Remove sufixos e espaços duplos
            clean_name = clean_name.split('  ')[0].strip()
            print(f"[DEBUG] Sucesso! Campanha: '{clean_name}'")
            return clean_name
        
        return None
    except Exception as e:
        print(f"[DEBUG] Erro na leitura dos dados: {e}")
        return None

async def finalize_campaign_only(server: str):
    async with async_playwright() as p:
        context, page, browser = await create_context_and_login(p, server=server)
        if not context: return False
        server_name = get_server_name(server)

        try:
            print(f"[{server_name}] 1. Navegando para Envio (Via API)...")
            await page.wait_for_timeout(3000)
            
            # Navegação passo a passo com esperas curtas
            await page.click('text=Discador Automático')
            await page.click('text=DA Preditivo')
            await asyncio.sleep(1)
            await page.click('text=Enviar', force=True)

            # Espera o botão de finalizar aparecer (prova que a tabela carregou)
            await page.wait_for_selector(SELETOR_BOTAO_FINALIZAR, state='visible', timeout=30000)

            print(f"[{server_name}] 2. Clicando em Finalizar...")
            botao = page.locator(SELETOR_BOTAO_FINALIZAR).first
            await botao.scroll_into_view_if_needed()
            await botao.click(force=True)

            await page.wait_for_selector(SELETOR_CONFIRMAR_FINALIZAR, state='visible', timeout=10000)
            await page.click(SELETOR_CONFIRMAR_FINALIZAR, force=True)
            
            return True
        except Exception as e:
            print(f"[{server_name}] ❌ Erro na finalização API: {e}")
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
            print(f"[{server_name}] 1. Navegando para Envio...")
            await page.wait_for_timeout(3000) 
            await page.click('text=Discador Automático')
            await page.click('text=DA Preditivo')
            await asyncio.sleep(1)
            await page.click('text=Enviar', force=True)

            # Extração do nome (que agora espera o AJAX)
            current_campaign = await get_current_campaign_name(page)

            if not current_campaign:
                print(f"[{server_name}] ⚠️ Alerta: Campanha não carregou. Tentando recarregar página...")
                await page.reload()
                await page.wait_for_timeout(5000)
                current_campaign = await get_current_campaign_name(page)
                if not current_campaign: return False

            print(f"[{server_name}] ✅ Campanha: {current_campaign}")

            print(f"[{server_name}] 2. Finalizando...")
            botao = page.locator(SELETOR_BOTAO_FINALIZAR).first
            await botao.wait_for(state='visible', timeout=20000)
            await botao.scroll_into_view_if_needed()
            await botao.click(force=True)
            
            await page.wait_for_selector(SELETOR_CONFIRMAR_FINALIZAR, state='visible', timeout=10000)
            await page.click(SELETOR_CONFIRMAR_FINALIZAR, force=True) 
            await page.wait_for_timeout(3000) 

            print(f"[{server_name}] 3. Reconfigurando Dropdowns...")
            # Dropdown Campanha
            await page.get_by_role("button", name="Escolha a opção").first.click()
            await page.wait_for_timeout(800) 
            await page.locator('div.dropdown-menu.open').get_by_role("option", name=current_campaign).click() 

            # Dropdown Telefone (Usando o seletor ID que vimos no seu HTML)
            await page.click('button[data-id="telefones"]')
            await page.wait_for_timeout(800) 
            await page.locator('div.dropdown-menu.open').get_by_role("option", name=current_campaign).click() 

            # Dropdown Fila
            await page.click('button[data-id="fila"]')
            await page.wait_for_timeout(800) 
            await page.locator('div.dropdown-menu.open').get_by_role("option", name=fila_name).click()

            await page.fill(SELETOR_INPUT_SAIDAS, SAIDAS_VALOR)
            await page.click(SELETOR_BOTAO_SUBIR_MAILING)
            await page.wait_for_timeout(2000) 

            print(f"[{server_name}] ✅ Restart OK!")
            return True
        except Exception as e:
            print(f"[{server_name}] ❌ Erro: {e}")
            return False
        finally:
            if browser: await browser.close()

if __name__ == '__main__':
    asyncio.run(restart_campaign(server="MG"))





















