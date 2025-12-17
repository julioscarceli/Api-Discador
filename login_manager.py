# utils/login_manager.py (Versão FINAL DE DEPLOY)

import os
from dotenv import load_dotenv
from playwright.async_api import Page, BrowserContext, Browser 
from config.settings import (
    LOGIN_URL_MG, 
    LOGIN_URL_SP, 
    BASE_URL_MG, 
    BASE_URL_SP,
    FILA_NOME_MG, 
    FILA_NOME_SP # <-- HEADLESS_MODE foi removido desta lista
)

# Carrega as variáveis de ambiente (Credenciais e Headless)
load_dotenv()

# --- Leitura de Credenciais e Controles de Ambiente (lidas do os.environ) ---
USUARIO = os.getenv("DISCADOR_USER")
SENHA = os.getenv("DISCADOR_PASS")

# HEADLESS_MODE é lido do .env ou Railway Secrets
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "False").lower() == "true"
# --------------------------------------------------------


# --- Funções Auxiliares (AGORA USAM O PARÂMETRO 'server') ---
def get_base_url(server: str) -> str:
    """Retorna a URL base (MG ou SP) baseada no parâmetro 'server'."""
    if server.upper() == "SP":
        return BASE_URL_SP
    return BASE_URL_MG

def get_login_url(server: str) -> str:
    """Retorna a URL de login (MG ou SP) baseada no parâmetro 'server'."""
    if server.upper() == "SP":
        return LOGIN_URL_SP
    return LOGIN_URL_MG

def get_fila_name(server: str) -> str:
    """Retorna o nome da Fila de Atendimento (MG ou SP) baseado no parâmetro 'server'."""
    if server.upper() == "SP":
        return FILA_NOME_SP
    return FILA_NOME_MG

def get_server_name(server: str) -> str:
    """Retorna o nome do servidor atual para logging."""
    return server.upper()


async def create_context_and_login(playwright_instance, server: str) -> tuple[BrowserContext, Page, Browser] | tuple[None, None, None]:
    """
    Cria o contexto do navegador, realiza o login e retorna (context, page, browser).
    Aplica tolerância de 60 segundos nas ações de rede críticas.
    """
    login_url = get_login_url(server) 
    server_name = get_server_name(server)
    browser = None 

    if not USUARIO or not SENHA:
        print(f"[{server_name}] ❌ Credenciais não configuradas. Configure DISCADOR_USER/PASS no .env ou Railway Secrets.")
        return None, None, None

    try:
        # 1. Cria o Navegador (Usando HEADLESS_MODE)
        browser = await playwright_instance.chromium.launch(headless=HEADLESS_MODE)
        context = await browser.new_context(ignore_https_errors=True) 
        page = await context.new_page()

        # 2. Navega para a URL de Login
        # Tolerância de 60s
        await page.goto(login_url, timeout=60000) 
        print(f"[{server_name}] Navegando para: {login_url}")

        # 3. Realiza o Login
        await page.fill('input[name="login"]', USUARIO) 
        await page.fill('input[name="password"]', SENHA)
        
        # Tolerância de 60s para o clique
        await page.click('button:has-text("Vamos lá")', timeout=60000) 
        
        # 4. Espera Pós-Login
        await page.wait_for_selector('a[href="#Discador_AutomáticoCollapse"]', state='visible', timeout=15000)
        
        print(f"[{server_name}] ✅ Login realizado e página autenticada!")
        return context, page, browser 

    except Exception as e:
        print(f"[{server_name}] ❌ Erro durante o processo de login ou inicialização: {e}")
        if 'browser' in locals() and browser:
            await browser.close()
        return None, None, None


