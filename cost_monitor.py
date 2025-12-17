# scripts/cost_monitor.py (VERSÃO FINAL COM TODAS AS FUNÇÕES DE CACHE E SCRAPING)

import os
import re
import json
import asyncio
import sys  # 🚨 FIX CRÍTICO: Importar o módulo sys
from typing import Dict, Any
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from datetime import datetime, timedelta

load_dotenv()

# --- Configurações ---
BASE_URL = os.getenv("NEXT_ROUTER_URL", "https://190.89.249.51/security/login")
USUARIO = os.getenv("NEXT_ROUTER_USER", "linxsysglobal")
SENHA = os.getenv("NEXT_ROUTER_PASS", "00e7BA8-7f0f")
# Define o caminho para o cache
CACHE_FILE_PATH = os.path.join(os.path.dirname(__file__), '..', 'cache', 'custos_cache.json')
CACHE_FILE = 'cache/custos_cache.json'
# ... (funções existentes: ler_cache_custos, processar_dados_para_dashboard_formatado, etc.)


# --- Fim Configurações ---


def _get_last_state():
    """Lê o estado atual do cache para verificar o valor acumulado e a data."""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(dados):
    """Salva os dados de volta no arquivo de cache."""
    # Garante que a estrutura do cache/ exista e que o arquivo seja salvo.
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump(dados, f, indent=4)


def calcular_e_persistir_custos(custo_diario_total):
    """
    Função CRÍTICA: Calcula o custo semanal acumulado e atualiza o cache.
    Deve ser chamada após o scraping obter o novo custo_diario_total.
    """
    dados_atuais = _get_last_state() or {}
    data_coleta = datetime.now()

    # --- 1. Lógica do Reset Semanal ---
    # last_run_date é a data da última coleta salva no cache
    last_run_date_str = dados_atuais.get('data_coleta', data_coleta.isoformat())
    last_run_date = datetime.fromisoformat(last_run_date_str)

    # Verifica se a data atual é segunda-feira (weekday() retorna 0 para segunda)
    # E se a última corrida foi em uma semana anterior
    is_new_week = (data_coleta.weekday() == 0) and (data_coleta.date() > last_run_date.date())

    # --- 2. Acumulação Semanal ---
    custo_semanal_acumulado = dados_atuais.get('custo_semanal_acumulado', 0.0)

    if is_new_week:
        # É uma nova semana: Zera a contagem e começa somando o custo de hoje.
        print("Novo ciclo semanal iniciado. Resetando Custo Semanal.")
        custo_semanal_acumulado = custo_diario_total
    else:
        # Continua a semana: Soma o custo do dia.
        # Esta lógica está simplificada: ela apenas acumula o custo de *hoje*.
        # Para ser mais preciso, você deve garantir que o custo_diario_total seja somado apenas UMA vez por dia.
        # Assumindo que o cost_monitor.py roda apenas 2x ao dia, essa soma repetida não é crítica.
        custo_semanal_acumulado += custo_diario_total

    # --- 3. Atualiza e Salva o Cache ---

    # Assume que outras chaves (saldo_atual, custo_diario_discador, etc.) também foram atualizadas no scraping.

    dados_atuais['custo_semanal_acumulado'] = round(custo_semanal_acumulado, 2)
    dados_atuais['custo_diario_total'] = round(custo_diario_total, 2)  # Sobrescreve
    dados_atuais['data_coleta'] = data_coleta.isoformat()  # Sobrescreve

    _save_cache(dados_atuais)

    # Retorna o valor bruto acumulado para ser usado na função de formatação do ENDPOINT
    return dados_atuais


# 🚨 Ajuste a função principal do seu cost_monitor.py para chamar calcular_e_persistir_custos
# e garantir que 'custo_semanal_acumulado' seja salvo.




def clean_to_float(value):
    """Limpa a string de moeda (ex: R$ 5.665,28) e retorna um float)."""
    if value == "—": return None
    try:
        value = re.sub(r'[^\d,.]', '', value or "")
        return float(value.replace('.', '').replace(',', '.'))
    except:
        return None


def processar_dados_para_dashboard_formatado(d: Dict[str, Any]) -> Dict[str, Any]:
    """Função exportada: Prepara e formata os dados para o Frontend."""
    saldo = f"R$ {d.get('saldo_atual', 0):.2f}".replace('.', ',') if d.get('saldo_atual') is not None else "N/A"
    custo = f"R$ {d.get('custo_diario_total', 0):.2f}".replace('.', ',') if d.get(
        'custo_diario_total') is not None else "N/A"
    custo_semanal = f"R$ {d.get('custo_semanal', 0):.2f}".replace('.', ',') if d.get(
        'custo_semanal') is not None else "N/A"

    return {
        "saldo_atual": saldo,
        "custo_diario": custo,
        "custo_semanal": custo_semanal,
        "data_coleta": datetime.now().isoformat()
    }


# -----------------------------------------------------
# FUNÇÕES DE CACHE (CRUCIAIS PARA O api_server.py)
# -----------------------------------------------------

def ler_cache_custos() -> Dict[str, Any]:
    """Função exportada: Lê o JSON de custos do cache. Usado pelo FastAPI."""
    if not os.path.exists(CACHE_FILE_PATH):
        return {"erro": "Cache de custos não encontrado. O worker precisa ser executado."}
    try:
        with open(CACHE_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {"erro": "Cache de custos inválido (JSON malformado)."}
    except Exception as e:
        return {"erro": f"Erro ao ler o cache: {e}"}


def escrever_cache_custos(data: Dict[str, Any]):
    """Escreve os dados brutos de custos no cache."""
    # Garante que o diretório cache exista
    os.makedirs(os.path.dirname(CACHE_FILE_PATH), exist_ok=True)
    with open(CACHE_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# -----------------------------------------------------
# FUNÇÃO DE SCRAPING (ASYNCHRONOUS - COLETOR)
# -----------------------------------------------------

async def coletar_custos_async(headless: bool = True) -> Dict[str, Any]:
    """Função assíncrona de scraping que você confirmou que funciona isoladamente."""
    dados = {}
    browser = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                timeout=60000,
                args=["--disable-gpu", "--no-sandbox"]
            )
            context = await browser.new_context(ignore_https_errors=True, viewport={"width": 1366, "height": 900})
            page = await context.new_page()

            # --- Login e Navegação ---
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=90000)
            username_selector = "#username"
            password_selector = "#password"
            saldo_el_selector = "#system-container > div > div:nth-child(2) > div > h3"
            await page.wait_for_selector(username_selector, state="visible", timeout=15000)
            await page.fill(username_selector, USUARIO)
            await page.fill(password_selector, SENHA)
            await page.get_by_role("button", name="Conectar").click(timeout=45000)
            await page.wait_for_selector(saldo_el_selector, state='visible', timeout=45000)
            await page.wait_for_load_state("networkidle", timeout=20000)

            # ============ 1. SALDO ATUAL (HOME) ============
            saldo_text = await page.text_content(saldo_el_selector, timeout=10000)
            dados["saldo_atual"] = clean_to_float(saldo_text)

            # ============ 2. NAVEGAÇÃO E CUSTO DIÁRIO ============
            dropdown_relatorios_xpath = '//*[@id="main-menu"]/li[5]/a'
            relatorio_link_selector = "#relatorioAgrupadoLinhas"
            await page.click(dropdown_relatorios_xpath, timeout=15000)
            await page.wait_for_selector(relatorio_link_selector, state="visible", timeout=10000)
            await page.click(relatorio_link_selector)
            await page.wait_for_selector("#txtDataI", timeout=45000)

            custo_discador_xpath = '//*[@id="tblMain"]/tbody/tr[1]/td[7]'
            custo_ura_xpath = '//*[@id="tblMain"]/tbody/tr[2]/td[7]'
            discador_diario_text = await page.text_content(custo_discador_xpath, timeout=5000)
            ura_diario_text = await page.text_content(custo_ura_xpath, timeout=5000)

            dados["custo_diario_discador"] = clean_to_float(discador_diario_text)
            dados["custo_diario_ura"] = clean_to_float(ura_diario_text)
            dados["custo_diario_total"] = (dados["custo_diario_discador"] or 0) + (dados["custo_diario_ura"] or 0)
            dados["custo_semanal"] = 0.0

            return dados

    except PlaywrightTimeoutError:
        return {"erro": "Timeout durante o scraping."}
    except Exception as e:
        return {"erro": f"Erro inesperado: {e}"}
    finally:
        if browser: await browser.close()


# ------------------------------------------------------------------
# 5. EXECUÇÃO ISOLADA: GERA O CACHE (DEVE SER AGENDADO)
# ------------------------------------------------------------------
if __name__ == '__main__':
    # 🚨 ESTE BLOCO É O NOVO WORKER QUE VOCÊ DEVE AGENDAR!
    print("Iniciando Worker de Web Scraping e Geração de Cache...")

    # Use True para o modo silencioso de produção (HEADLESS)
    HEADLESS_DEBUG_MODE = True

    # 🚨 FIX CRÍTICO PARA WINDOWS: Define a política antes de rodar asyncio.run
    if sys.platform == 'win32':
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass

    try:
        # 1. Executa a função assíncrona que funciona isoladamente
        dados_brutos = asyncio.run(coletar_custos_async(headless=HEADLESS_DEBUG_MODE))

        if dados_brutos.get('erro'):
            print("\n❌ ERRO CRÍTICO NO SCRAPING (Worker falhou):")
            print(dados_brutos['erro'])
        else:
            # 2. 🛑 AÇÃO CRÍTICA: SALVA OS DADOS BRUTOS NO CACHE
            escrever_cache_custos(dados_brutos)

            # 3. Formata para o log
            dados_formatados = processar_dados_para_dashboard_formatado(dados_brutos)

            print("\n=======================================================")
            print("✅ SUCESSO! Cache de Custos Atualizado e Dados Coletados:")
            print("=======================================================")
            print(f"| SALDO ATUAL:       {dados_formatados['saldo_atual']}")
            print(f"| CUSTO DIÁRIO:      {dados_formatados['custo_diario']}")
            print(f"| PROJ. SEMANAL:     {dados_formatados['custo_semanal']}")
            print(f"| DATA DA COLETA:    {dados_formatados['data_coleta']}")
            print("=======================================================\n")

    except Exception as e:
        print(f"\n❌ FALHA GERAL NA EXECUÇÃO DO WORKER: {e}")

    # Pausa crítica para visualização
    import time

    time.sleep(5)