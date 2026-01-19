# utils/login_manager.py (Versão FINAL DE DEPLOY - 100% INTEGRADA)

import os
import asyncio
from dotenv import load_dotenv
from playwright.async_api import Page, BrowserContext, Browser, async_playwright
from config.settings import (
    LOGIN_URL_MG, 
    LOGIN_URL_SP, 
    BASE_URL_MG, 
    BASE_URL_SP,
    FILA_NOME_MG, 
    FILA_NOME_SP
)

# Carrega as variáveis de ambiente (Credenciais e Headless)
load_dotenv()

# --- Leitura de Credenciais e Controles de Ambiente (lidas do os.environ) ---
USUARIO = os.getenv("DISCADOR_USER")
SENHA = os.getenv("DISCADOR_PASS")

# HEADLESS_MODE é lido do .env ou Railway Secrets
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "False").lower() == "true"
# --------------------------------------------------------


# --- Funções Auxiliares (MANTIDAS CONFORME SEU ORIGINAL) ---
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


# utils/login_manager.py (Trecho Otimizado)

async def create_context_and_login(playwright_instance, server: str):
    login_url = get_login_url(server) 
    server_name = get_server_name(server)
    browser = None 

    try:
        browser = await playwright_instance.chromium.launch(headless=HEADLESS_MODE)
        context = await browser.new_context(ignore_https_errors=True) 
        page = await context.new_page()

        # BLOQUEIO DE RECURSOS: Impede o carregamento de imagens e CSS pesado para ganhar velocidade
        await page.route("**/*.{png,jpg,jpeg,css}", lambda route: route.abort())

        # Reduzimos a exigência de espera: "commit" já é suficiente para começar a preencher
        print(f"[{server_name}] Acessando: {login_url}")
        await page.goto(login_url, timeout=90000, wait_until="commit") 

        # Pequena pausa para garantir que os inputs foram renderizados
        await page.wait_for_selector('input[name="login"]', timeout=10000)

        await page.fill('input[name="login"]', USUARIO) 
        await page.fill('input[name="password"]', SENHA)
        
        # Clica e aguarda apenas o necessário
        await page.click('button:has-text("ENTRAR")', timeout=60000) 
        
        # Espera o seletor principal (aumentamos a tolerância aqui)
        await page.wait_for_selector('a[href="#Discador_AutomáticoCollapse"]', state='visible', timeout=45000)
        
        print(f"[{server_name}] ✅ Login realizado!")
        return context, page, browser 

    except Exception as e:
        print(f"[{server_name}] ❌ Falha técnica: {e}")
        if browser:
            await browser.close()
        return None, None, None


# --- 🚨 NOVA CLASSE: INTEGRADA PARA CAPTURA DE SESSÃO API ---
class LoginManager:
    """
    Classe que orquestra a captura do PHPSESSID para permitir
    que a API realize ações autenticadas sem retornar HTML de login.
    """
    
    async def get_active_session(self, server: str) -> dict:
        """
        Inicia um navegador temporário, realiza o login via UI
        e extrai os cookies de sessão.
        """
        server_name = get_server_name(server)
        print(f"[{server_name}] 🔑 Capturando sessão ativa para vínculo de campanha...")
        
        async with async_playwright() as p:
            # Reutiliza sua função original para garantir consistência
            context, page, browser = await create_context_and_login(p, server)
            
            if not context:
                print(f"[{server_name}] ❌ Não foi possível capturar a sessão.")
                return {}

            # Extrai os cookies gerados pelo navegador após o login de sucesso
            browser_cookies = await context.cookies()
            
            # Fecha o navegador imediatamente para liberar memória (Importante no Railway)
            await browser.close()

            # Formata o dicionário de cookies para o formato esperado pelo HTTPIX/Requests
            session_dict = {}
            for cookie in browser_cookies:
                if cookie['name'] == 'PHPSESSID':
                    session_dict['PHPSESSID'] = cookie['value']
            
            if 'PHPSESSID' in session_dict:
                print(f"[{server_name}] 🎫 PHPSESSID capturado com sucesso.")
            else:
                print(f"[{server_name}] ⚠️ PHPSESSID não encontrado nos cookies.")
                
            return session_dict






