# scripts/restart_campaign.py

import asyncio
import re
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login, get_fila_name, get_server_name
from config.settings import SAIDAS_VALOR

# --- Constantes do Script (Seletores Validados via HTML enviado) ---
SELETOR_TABELA_CONTAINER = '#Tabela'
# Seleciona o botão pela classe técnica e texto exato
SELETOR_BOTAO_FINALIZAR = 'button.btParar:has-text("Finalizar Campanha")'
SELETOR_CONFIRMAR_FINALIZAR = 'button:has-text("Sim, pode finalizar!")'
SELETOR_INPUT_SAIDAS = '#saida'
SELETOR_BOTAO_SUBIR_MAILING = '#btCampanha1'
SELETOR_PAINEL_PENDENTES = 'text=Contatos pendentes'

# Seletores de Abertura de Dropdowns
SELETOR_BOTAO_FILA_ABRIR = 'xpath=//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[6]/div/div[1]/button'
SELETOR_BOTAO_TELEFONE_ABRIR = 'xpath=//*[@id="Discador"]/div[1]/div/div/div/div[2]/div[1]/div[3]/div/div[1]/button'

# NOVO SELETOR HIERÁRQUICO
SELETOR_LISTA_ABERTA_ITEM = 'div.dropdown-menu.open'


async def get_current_campaign_name(page) -> str | None:
    """
    Captura o nome da campanha extraindo diretamente da lista do footer do card.
    """
    try:
        # 1. Aguarda a tabela principal ser preenchida pelo JS do discador
        print("[DEBUG] Aguardando renderização da tabela de campanhas...")
        await page.wait_for_selector(SELETOR_TABELA_CONTAINER, state='visible', timeout=30000)
        
        # 2. Localiza o texto após o ícone 'assignment' (que é o título da Campanha no seu HTML)
        # O seletor busca o texto que contém MAILING_DISCADOR dentro do card
        campaign_element = page.locator('.card-footer .stats').filter(has_text="MAILING_DISCADOR")
        
        await campaign_element.first.wait_for(state='visible', timeout=15000)
        
        raw_text = await campaign_element.first.inner_text()
        print(f"[DEBUG] Texto bruto do footer: {raw_text}")

        # 3. Limpeza rigorosa: pega apenas a linha que contém o nome da campanha
        for line in raw_text.split('\n'):
            if "MAILING_DISCADOR" in line.upper():
                # Remove o prefixo do ícone se houver e limpa espaços/porcentagens
                clean_name = line.replace('assignment:', '').replace('assignment', '').strip()
                clean_name = clean_name.split('  ')[0].strip()
                clean_name = re.sub(r'\d+\.?\d*%', '', clean_name).strip()
                
                print(f"[DEBUG] Nome identificado: '{clean_name}'")
                return clean_name
        
        return None
    except Exception as e:
        print(f"[DEBUG] Erro ao extrair nome via footer: {e}")
        return None


# --- FUNÇÃO ISOLADA PARA LIMPEZA (CHAMADA PELA API E DAILY WORKER) ---
async def finalize_campaign_only(server: str):
    """Navega até a página de envio e executa apenas a finalização da campanha atual."""
    async with async_playwright() as p:
        context, page, browser = await create_context_and_login(p, server=server)
        if not context: return False
        server_name = get_server_name(server)

        try:
            print(f"[{server_name}] 1. Navegando para Finalização via API...")
            await page.wait_for_timeout(5000)
            await page.get_by_role("link", name="send Discador Automático").click()
            await page.wait_for_timeout(500)
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            await page.wait_for_timeout(1000)
            await page.get_by_text("Enviar").click(force=True)

            # Espera a tabela carregar antes de procurar o botão
            await page.wait_for_selector(SELETOR_TABELA_CONTAINER, state='visible', timeout=20000)

            print(f"[{server_name}] 2. Finalizando Campanha via .btParar...")
            botao = page.locator(SELETOR_BOTAO_FINALIZAR).first
            await botao.wait_for(state='visible', timeout=30000)
            await botao.scroll_into_view_if_needed()
            await botao.click(force=True)

            await page.wait_for_selector(SELETOR_CONFIRMAR_FINALIZAR, state='visible', timeout=15000)
            await page.click(SELETOR_CONFIRMAR_FINALIZAR, force=True)

            print(f"[{server_name}] ✅ Finalização concluída.")
            await page.wait_for_timeout(3000)
            return True
        except Exception as e:
            print(f"[{server_name}] ❌ Erro na finalização via API: {e}")
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
            print(f"[{server_name}] 1. Iniciando Rotina de Restart...")
            await page.wait_for_timeout(5000) 
            await page.get_by_role("link", name="send Discador Automático").click()
            await page.wait_for_timeout(500) 
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            await page.wait_for_timeout(1000)
            await page.get_by_text("Enviar").click(force=True)

            # Extração de nome aguardando a tabela
            current_campaign = await get_current_campaign_name(page)
            if not current_campaign: return False

            print(f"[{server_name}] ✅ Campanha atual: {current_campaign}")

            print(f"[{server_name}] 2. Finalizando Campanha ativa...")
            botao = page.locator(SELETOR_BOTAO_FINALIZAR).first
            await botao.wait_for(state='visible', timeout=30000)
            await botao.scroll_into_view_if_needed()
            await botao.click(force=True)
            
            await page.wait_for_selector(SELETOR_CONFIRMAR_FINALIZAR, state='visible', timeout=15000)
            await page.click(SELETOR_CONFIRMAR_FINALIZAR, force=True) 
            await page.wait_for_timeout(3000) 

            print(f"[{server_name}] 3. Reconfigurando Dropdowns...")
            await page.get_by_role("button", name="Escolha a option").first.click()
            await page.wait_for_timeout(800) 
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=current_campaign).click(timeout=20000) 

            await page.click(SELETOR_BOTAO_TELEFONE_ABRIR)
            await page.wait_for_timeout(800) 
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=current_campaign).click(timeout=20000) 

            await page.click(SELETOR_BOTAO_FILA_ABRIR)
            await page.wait_for_timeout(800) 
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=fila_name).click(timeout=20000)

            await page.fill(SELETOR_INPUT_SAIDAS, SAIDAS_VALOR)
            await page.click(SELETOR_BOTAO_SUBIR_MAILING)
            await page.wait_for_timeout(2000) 

            print(f"[{server_name}] ✅ Restart completo!")
            return True
        except Exception as e:
            print(f"[{server_name}] ❌ Erro no restart: {e}")
            return False
        finally:
            if browser: await browser.close()


if __name__ == '__main__':
    import asyncio
    asyncio.run(restart_campaign(server="MG"))

















