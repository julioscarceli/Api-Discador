# scripts/restart_campaign.py

import asyncio
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


# scripts/restart_campaign.py (Ajuste de Precisão no Nome)

async def get_current_campaign_name(page) -> str | None:
    """
    Captura o nome exato da campanha, limpando duplicatas e espaços.
    """
    try:
        # Aguarda o elemento de pendentes carregar
        await page.wait_for_selector(SELETOR_PAINEL_PENDENTES, state='visible', timeout=20000) 
        
        # Localiza o texto que contém o padrão do seu mailing
        # O seletor 'text=/MAILING_DISCADOR/' é mais preciso para o seu caso
        campaign_elements = page.locator('text=/MAILING_DISCADOR/')
        all_texts = await campaign_elements.all_inner_texts()

        if not all_texts:
            return None

        # Pega o primeiro texto encontrado
        raw_text = all_texts[0].strip()
        
        # LIMPEZA CRÍTICA: Se o texto vier com quebra de linha ou duplicado (como no print)
        # nós pegamos apenas a primeira parte antes da quebra de linha ou do espaço duplo
        clean_name = raw_text.split('\n')[0].split('  ')[0].strip()
        
        # Remove também qualquer resquício de porcentagem se houver (ex: 11.11%)
        clean_name = clean_name.replace('0.00%', '').replace('11.11%', '').strip()

        print(f"[DEBUG] Nome final limpo para seleção: '{clean_name}'")
        return clean_name
    except Exception as e:
        print(f"[DEBUG] Erro ao extrair nome: {e}")
        return None


# --- FUNÇÃO ISOLADA PARA LIMPEZA (CHAMADA PELO DAILY WORKER) ---
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
            print(f"[{server_name}] 1. Navegando para Finalização de Campanha...")

            # Estabilização pós-login
            await page.wait_for_timeout(5000)

            # Navegação (Clique Discador Automático -> Preditivo -> Enviar)
            await page.get_by_role("link", name="send Discador Automático").click()
            await page.wait_for_timeout(200)
            await page.get_by_role("link", name="DA Preditivo").click()
            await page.wait_for_timeout(1000)
            
            # Ajuste de clique forçado para evitar interceptação de menus
            await page.get_by_text("Enviar").click(force=True)

            # Extração (Necessário para a próxima etapa, mas não para a finalização em si)
            current_campaign = await get_current_campaign_name(page)

            if not current_campaign:
                print(
                    f"[{server_name}] ⚠️ Alerta: Nome da campanha não encontrado para log. Prosseguindo com a finalização.")

            print(f"[{server_name}] 2. Finalizando Campanha atual via UI...")

            # Finalização (O ponto final da rotina de limpeza)
            await page.wait_for_selector(SELETOR_BOTAO_FINALIZAR, state='visible', timeout=10000)
            await page.click(SELETOR_BOTAO_FINALIZAR)
            await page.click(SELETOR_CONFIRMAR_FINALIZAR)
            await page.wait_for_timeout(1000)

            print(f"[{server_name}] ✅ Campanha antiga finalizada com sucesso.")
            return True

        except Exception as e:
            print(f"[{server_name}] ❌ Erro durante a FINALIZAÇÃO da campanha: {e}")
            return False

        finally:
            if browser:  # ✅ GARANTIA DE RECURSOS: Fecha o navegador após cada ciclo.
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
            print(f"[{server_name}] 1. Navegando para Envio de Campanhas e extraindo nome da campanha...")

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

            print(f"[{server_name}] 2. Finalizando Campanha atual...")
            await page.wait_for_selector(SELETOR_BOTAO_FINALIZAR, state='visible', timeout=10000)
            await page.click(SELETOR_BOTAO_FINALIZAR)
            
            # ✅ CORREÇÃO: Usando a constante correta
            await page.click(SELETOR_CONFIRMAR_FINALIZAR) 
            await page.wait_for_timeout(1000) 

            # ----------------------------------------------------
            # ETAPA 3: RECONFIGURAÇÃO E DISPARO (AÇÕES OTIMIZADAS/ROBUSTAS)
            # ----------------------------------------------------
            print(f"[{server_name}] 3. Reconfigurando e disparando o mailing...")

            # AÇÃO A: Selecionar a CAMPANHA
            await page.get_by_role("button", name="Escolha a opção").first.click()
            # ✅ CORREÇÃO: Restaurando espera de sincronia de 500ms
            await page.wait_for_timeout(500) 
            
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=current_campaign).wait_for(state='visible', timeout=10000) 
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=current_campaign).click(
                timeout=20000) 

            # AÇÃO B: SELECIONAR TELEFONE/MAILING
            await page.click(SELETOR_BOTAO_TELEFONE_ABRIR)
            # ✅ CORREÇÃO: Restaurando espera de sincronia de 500ms
            await page.wait_for_timeout(500) 
            
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=current_campaign).wait_for(state='visible', timeout=10000)
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=current_campaign).click(
                timeout=20000) 

            # AÇÃO C: Selecionar a FILA DE ATENDIMENTO
            await page.click(SELETOR_BOTAO_FILA_ABRIR)
            # ✅ CORREÇÃO: Restaurando espera de sincronia de 500ms
            await page.wait_for_timeout(500) 
            
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=fila_name).wait_for(state='visible', timeout=10000)
            await page.locator(SELETOR_LISTA_ABERTA_ITEM).get_by_role("option", name=fila_name).click(timeout=20000)

            # AÇÃO D: Preencher Saídas
            await page.fill(SELETOR_INPUT_SAIDAS, SAIDAS_VALOR)

            # AÇÃO E: Clicar no BOTÃO DE ENVIO (Subir Mailing)
            await page.click(SELETOR_BOTAO_SUBIR_MAILING)
            
            await page.wait_for_timeout(2000) 

            print(f"[{server_name}] ✅ Campanhas reconfigurada e subida com sucesso!")
            return True

        except Exception as e:
            print(f"[{server_name}] ❌ Erro durante a automação do restart: {e}")
            return False

        finally:
            if browser: # ✅ GARANTIA DE RECURSOS: Fecha o navegador após cada ciclo.
                await browser.close()


if __name__ == '__main__':
    import asyncio
    asyncio.run(restart_campaign(server="MG"))
    # Loga, extrai nome da campanha em execução, finaliza campanha,
    # reconfigura os 3 dropdowns (Campanha, Telefone, Fila) e envia o mailing.










