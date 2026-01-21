# scripts/restart_campaign.py

import asyncio
import re
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login, get_fila_name, get_server_name
from config.settings import SAIDAS_VALOR

# --- Constantes de Seletores (Otimizados para AJAX/Dynamic DOM) ---
SELETOR_BOTAO_FINALIZAR = 'button.btParar'
# Seletor duplo para garantir que pegue o botão de confirmação do SweetAlert
SELETOR_CONFIRMAR_FINALIZAR = 'button.swal2-confirm, button:has-text("Sim, pode finalizar!")'
SELETOR_INPUT_SAIDAS = '#saida'
SELETOR_BOTAO_SUBIR_MAILING = '#btCampanha1'
# Seletor para garantir que o AJAX preencheu a tabela
SELETOR_CARD_STATS = '.card-stats' 

async def get_current_campaign_name(page) -> str | None:
    """
    Extrai o nome da campanha aguardando a renderização completa do AJAX.
    """
    try:
        # 1. Aguarda a rede ficar ociosa e o card stats aparecer (Sincronia AJAX)
        print("[DEBUG] Aguardando estabilização da tabela dinâmica...")
        await page.wait_for_load_state("networkidle", timeout=30000)
        await page.wait_for_selector(SELETOR_CARD_STATS, state='visible', timeout=30000)
        
        # 2. Localiza o bloco de texto após o ícone de 'assignment'
        stats_block = page.locator('.stats').filter(has_text="MAILING_DISCADOR")
        await stats_block.first.wait_for(state='visible', timeout=15000)
        
        text_content = await stats_block.first.inner_text()
        print(f"[DEBUG] Conteúdo bruto: {text_content.strip()}")

        # 3. Extração via Regex para evitar erros de 'startswith' com ícones
        match = re.search(r'MAILING_DISCADOR[^\n\r]+', text_content)
        if match:
            # Limpa o nome removendo o label do ícone e espaços extras
            clean_name = match.group(0).replace('assignment:', '').strip()
            # Pega apenas a primeira parte antes de qualquer espaço duplo ou %
            final_name = clean_name.split('  ')[0].strip()
            print(f"[DEBUG] Nome capturado com sucesso: '{final_name}'")
            return final_name
        
        return None
    except Exception as e:
        print(f"[DEBUG] Falha ao extrair nome da campanha: {e}")
        return None

async def finalize_campaign_only(server: str):
    """Executa apenas a finalização (Limpeza disparada pela API)."""
    async with async_playwright() as p:
        context, page, browser = await create_context_and_login(p, server=server)
        if not context: return False
        server_name = get_server_name(server)

        try:
            print(f"[{server_name}] 1. Navegando para Limpeza UI...")
            await page.wait_for_timeout(5000)
            await page.get_by_role("link", name="send Discador Automático").click()
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            await asyncio.sleep(2) # Pausa para o carregamento do frame
            await page.get_by_text("Enviar").click(force=True)

            print(f"[{server_name}] 2. Finalizando via Script (Ação Forçada)...")
            # Aguarda o botão existir no código e clica via JS direto (ignora loaders na frente)
            botao = page.locator(SELETOR_BOTAO_FINALIZAR).first
            await botao.wait_for(state='attached', timeout=30000)
            await botao.evaluate("node => node.click()")

            # Confirmação no modal
            confirmar = page.locator(SELETOR_CONFIRMAR_FINALIZAR).first
            await confirmar.wait_for(state='attached', timeout=15000)
            await confirmar.evaluate("node => node.click()")
            
            print(f"[{server_name}] ✅ Finalização via API concluída.")
            return True
        except Exception as e:
            print(f"[{server_name}] ❌ Falha na limpeza via API: {e}")
            return False
        finally:
            if browser: await browser.close()

async def restart_campaign(server: str): 
    """Rotina completa de Restart (Monitor)."""
    async with async_playwright() as p:
        context, page, browser = await create_context_and_login(p, server=server)
        if not context: return False

        server_name = get_server_name(server)
        fila_name = get_fila_name(server)

        try:
            print(f"[{server_name}] 1. Sincronizando com a página de Envio...")
            await page.wait_for_timeout(5000) 
            await page.get_by_role("link", name="send Discador Automático").click()
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            await asyncio.sleep(2)
            await page.get_by_text("Enviar").click(force=True)

            # Extração do nome (com espera AJAX interna)
            current_campaign = await get_current_campaign_name(page)

            if not current_campaign:
                print(f"[{server_name}] ⚠️ Alerta: Dados não carregaram. Forçando atualização (F5)...")
                await page.reload()
                await page.wait_for_timeout(5000)
                current_campaign = await get_current_campaign_name(page)
                if not current_campaign: return False

            print(f"[{server_name}] ✅ Reiniciando campanha: {current_campaign}")

            # Etapa de Parada Forçada
            botao = page.locator(SELETOR_BOTAO_FINALIZAR).first
            await botao.wait_for(state='attached', timeout=30000)
            await botao.evaluate("node => node.click()")
            
            confirmar = page.locator(SELETOR_CONFIRMAR_FINALIZAR).first
            await confirmar.wait_for(state='attached', timeout=15000)
            await confirmar.evaluate("node => node.click()")
            
            await page.wait_for_timeout(4000) # Aguarda o sistema processar a parada

            print(f"[{server_name}] 3. Configurando Dropdowns...")
            # Seleciona Mailing nos 2 primeiros dropdowns (Campanha e Telefone)
            # Usamos data-id para precisão total encontrada no seu código fonte
            
            # Dropdown 1: Campanha
            await page.get_by_role("button", name="Escolha a opção").first.click()
            await page.wait_for_timeout(1000) 
            await page.locator('div.dropdown-menu.open').get_by_role("option", name=current_campaign).click() 

            # Dropdown 2: Telefone
            await page.click('button[data-id="telefones"]')
            await page.wait_for_timeout(1000) 
            await page.locator('div.dropdown-menu.open').get_by_role("option", name=current_campaign).click() 

            # Dropdown 3: Fila
            await page.click('button[data-id="fila"]')
            await page.wait_for_timeout(1000) 
            await page.locator('div.dropdown-menu.open').get_by_role("option", name=fila_name).click()

            # Disparo
            await page.fill(SELETOR_INPUT_SAIDAS, SAIDAS_VALOR)
            await page.click(SELETOR_BOTAO_SUBIR_MAILING)
            
            print(f"[{server_name}] ✅ Ciclo de Restart finalizado com sucesso!")
            return True
        except Exception as e:
            print(f"[{server_name}] ❌ Erro durante o restart: {e}")
            return False
        finally:
            if browser: await browser.close()

if __name__ == '__main__':
    asyncio.run(restart_campaign(server="MG"))























