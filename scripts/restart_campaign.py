# scripts/restart_campaign.py

import asyncio
import re
from playwright.async_api import async_playwright
from utils.login_manager import create_context_and_login, get_fila_name, get_server_name
from config.settings import SAIDAS_VALOR

# --- Constantes do Script (Seletores Validados) ---
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
    Captura o nome da campanha com maior tolerância e verificação de carga.
    """
    try:
        # 1. Aguarda a página estabilizar após o clique em 'Enviar'
        print("[DEBUG] Aguardando estabilização da rede para ler campanha...")
        await page.wait_for_load_state("networkidle", timeout=30000)
        
        # 2. Tenta localizar o seletor com um timeout maior (30s)
        try:
            await page.wait_for_selector(SELETOR_PAINEL_PENDENTES, state='visible', timeout=30000)
        except:
            print("[DEBUG] Aviso: 'Contatos pendentes' não apareceu, tentando busca direta por MAILING...")

        # 3. Busca flexível por qualquer elemento que contenha MAILING_DISCADOR
        campaign_elements = page.locator('text=/MAILING_DISCADOR/i')
        
        # Espera pelo menos um elemento de mailing estar visível
        await campaign_elements.first.wait_for(state='visible', timeout=15000)
        
        all_texts = await campaign_elements.all_inner_texts()
        print(f"[DEBUG] Textos brutos capturados: {all_texts}")

        if not all_texts:
            return None

        # 4. Limpeza rigorosa (Baseada no print: texto duplicado e quebras de linha)
        raw_text = all_texts[0].strip()
        clean_name = raw_text.split('\n')[0].split('  ')[0].strip()
        
        # Remove sufixos de porcentagem se o Playwright capturar o label junto
        clean_name = re.sub(r'\d+\.?\d*%', '', clean_name).strip()

        print(f"[DEBUG] Nome identificado para o dropdown: '{clean_name}'")
        return clean_name

    except Exception as e:
        print(f"[DEBUG] Erro crítico na extração: {e}")
        return None


# --- FUNÇÃO ISOLADA PARA LIMPEZA (CHAMADA PELA API E DAILY WORKER) ---
async def finalize_campaign_only(server: str):
    """Navega até a página de envio e executa apenas a finalização da campanha atual."""
    async with async_playwright() as p:
        # 1. Recebe os 3 objetos (context, page, browser)
        context, page, browser = await create_context_and_login(p, server=server)

        if not context:
            return False

        server_name = get_server_name(server)

        try:
            # ----------------------------------------------------
            # ETAPA 1: NAVEGAÇÃO E EXTRAÇÃO DO NOME DA CAMPANHA
            # ----------------------------------------------------
            print(f"[{server_name}] 1. Navegando para Finalização de Campanha via API...")

            # Estabilização pós-login
            await page.wait_for_timeout(5000)

            # Navegação (Clique Discador Automático -> Preditivo -> Enviar)
            await page.get_by_role("link", name="send Discador Automático").click()
            await page.wait_for_timeout(500)
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            await page.wait_for_timeout(1000)
            
            # Ajuste de clique forçado para evitar interceptação de menus
            await page.get_by_text("Enviar").click(force=True)

            # ----------------------------------------------------
            # ETAPA 2: FINALIZAÇÃO OBRIGATÓRIA DA CAMPANHA
            # ----------------------------------------------------
            print(f"[{server_name}] 2. Executando clique de finalização robusto...")
            
            # CORREÇÃO DO SELETOR: Usando localizadores de texto do Playwright para evitar erro de parse CSS
            botao = page.get_by_role("button").get_by_text(re.compile(r"Finalizar Campanha", re.IGNORECASE)).first
            
            # Tenta seletor alternativo via classe se o texto falhar
            if await botao.count() == 0:
                botao = page.locator("button.btParar").first

            await botao.wait_for(state='visible', timeout=30000)
            
            # Rola até o botão para garantir visibilidade
            await botao.scroll_into_view_if_needed()
            await botao.click(force=True)

            # Confirmação (Sim, pode finalizar!)
            await page.wait_for_selector(SELETOR_CONFIRMAR_FINALIZAR, state='visible', timeout=15000)
            await page.click(SELETOR_CONFIRMAR_FINALIZAR, force=True)

            print(f"[{server_name}] ✅ Campanha antiga finalizada com sucesso via API.")
            await page.wait_for_timeout(3000)
            return True

        except Exception as e:
            print(f"[{server_name}] ❌ Erro durante a FINALIZAÇÃO via API: {e}")
            return False

        finally:
            if browser:  # ✅ GARANTIA DE RECURSOS
                await browser.close()

async def restart_campaign(server: str): 
    async with async_playwright() as p:
        # 1. Recebe os 3 objetos (context, page, browser)
        context, page, browser = await create_context_and_login(p, server=server)

        if not context:
            return False

        server_name = get_server_name(server)
        fila_name = get_fila_name(server)

        try:
            # ----------------------------------------------------
            # ETAPA 1: NAVEGAÇÃO, EXTRAÇÃO E FINALIZAÇÃO
            # ----------------------------------------------------
            print(f"[{server_name}] 1. Iniciando Rotina de Restart...")

            # Estabilização pós-login
            await page.wait_for_timeout(5000) 

            # Navegação Robusta (Clique Discador Automático -> Preditivo -> Enviar)
            await page.get_by_role("link", name="send Discador Automático").click()
            await page.wait_for_timeout(500) 
            
            # Uso de force=True para evitar interceptação de menus dropdown
            await page.get_by_role("link", name="DA Preditivo").click(force=True)
            await page.wait_for_timeout(1000)
            
            enviar_btn = page.get_by_text("Enviar")
            await enviar_btn.wait_for(state='visible', timeout=15000)
            await enviar_btn.click(force=True)

            current_campaign = await get_current_campaign_name(page)

            if not current_campaign:
                print(f"[{server_name}] ⚠️ Alerta: Não foi possível obter o nome da campanha. Abortando restart.")
                return False

            print(f"[{server_name}] ✅ Campanha atual identificada: {current_campaign}")

            # ----------------------------------------------------
            # ETAPA 2: FINALIZAÇÃO OBRIGATÓRIA DA CAMPANHA
            # ----------------------------------------------------
            print(f"[{server_name}] 2. Finalizando Campanha ativa para reimportar...")
            
            # CORREÇÃO DO SELETOR: Usando localizadores de texto do Playwright para evitar erro de parse CSS
            botao = page.get_by_role("button").get_by_text(re.compile(r"Finalizar Campanha", re.IGNORECASE)).first
            
            # Tenta seletor alternativo via classe se o texto falhar
            if await botao.count() == 0:
                botao = page.locator("button.btParar").first

            await botao.wait_for(state='visible', timeout=30000)
            
            # Garante que o botão esteja visível na tela antes de clicar
            await botao.scroll_into_view_if_needed()
            await botao.click(force=True)
            
            # Confirmação
            await page.wait_for_selector(SELETOR_CONFIRMAR_FINALIZAR, state='visible', timeout=15000)
            await page.click(SELETOR_CONFIRMAR_FINALIZAR, force=True) 
            
            await page.wait_for_timeout(3000) 

            # ----------------------------------------------------
            # ETAPA 3: RECONFIGURAÇÃO E DISPARO (AÇÕES OTIMIZADAS/ROBUSTAS)
            # ----------------------------------------------------
            print(f"[{server_name}] 3. Selecionando mailing nos dropdowns...")

            # AÇÃO A: Selecionar a CAMPANHA
            await page.get_by_role("button", name="Escolha a opção").first.click()
            await page.wait_for_timeout(500) 
            
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=current_campaign).wait_for(state='visible', timeout=10000) 
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=current_campaign).click(timeout=20000) 

            # AÇÃO B: SELECIONAR TELEFONE/MAILING
            await page.click(SELETOR_BOTAO_TELEFONE_ABRIR)
            await page.wait_for_timeout(500) 
            
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=current_campaign).wait_for(state='visible', timeout=10000)
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=current_campaign).click(timeout=20000) 

            # AÇÃO C: Selecionar a FILA DE ATENDIMENTO
            await page.click(SELETOR_BOTAO_FILA_ABRIR)
            await page.wait_for_timeout(500) 
            
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=fila_name).wait_for(state='visible', timeout=10000)
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=fila_name).click(timeout=20000)

            # AÇÃO D: Preencher Saídas
            await page.fill(SELETOR_INPUT_SAIDAS, SAIDAS_VALOR)

            # AÇÃO E: Clicar no BOTÃO DE ENVIO (Subir Mailing)
            await page.click(SELETOR_BOTAO_SUBIR_MAILING)
            
            await page.wait_for_timeout(2000) 

            print(f"[{server_name}] ✅ Restart completo e mailing subindo!")
            return True

        except Exception as e:
            print(f"[{server_name}] ❌ Erro durante a automação do restart: {e}")
            return False

        finally:
            if browser: # ✅ GARANTIA DE RECURSOS
                await browser.close()


if __name__ == '__main__':
    import asyncio
    asyncio.run(restart_campaign(server="MG"))














