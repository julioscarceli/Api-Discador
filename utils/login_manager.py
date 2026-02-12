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

# --- Leitura de Credenciais e Controles de Ambiente ---
USUARIO = os.getenv("DISCADOR_USER", "SOMA")
SENHA = os.getenv("DISCADOR_PASS", "123456")

# HEADLESS_MODE é lido do Railway Secrets (Sempre True em produção)
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "True").lower() == "true"

def get_base_url(server: str) -> str:
    if server.upper() == "SP": return BASE_URL_SP
    return BASE_URL_MG

def get_login_url(server: str) -> str:
    if server.upper() == "SP": return LOGIN_URL_SP
    return LOGIN_URL_MG

def get_fila_name(server: str) -> str:
    if server.upper() == "SP": return FILA_NOME_SP
    return FILA_NOME_MG

def get_server_name(server: str) -> str:
    return server.upper()

async def create_context_and_login(playwright_instance, server: str):
    login_url = get_login_url(server) 
    server_name = get_server_name(server)
    browser = None 

    try:
        browser = await playwright_instance.chromium.launch(headless=HEADLESS_MODE)
        context = await browser.new_context(ignore_https_errors=True) 
        page = await context.new_page()

        # BLOQUEIO DE RECURSOS: Aumenta a velocidade e economiza RAM no Railway
        await page.route("**/*.{png,jpg,jpeg,css}", lambda route: route.abort())

        print(f"[{server_name}] Acessando: {login_url}")
        await page.goto(login_url, timeout=90000, wait_until="commit") 

        user_input = page.locator('input[name="login"], input[placeholder*="Usuá"]').first
        await user_input.wait_for(state="attached", timeout=15000)

        await user_input.evaluate("(el, val) => el.value = val", USUARIO)
        await page.locator('input[type="password"]').first.evaluate("(el, val) => el.value = val", SENHA)
        
        btn_entrar = page.locator('button:has-text("ENTRAR")').first
        await btn_entrar.wait_for(state="attached", timeout=15000)
        
        print(f"[{server_name}] Disparando clique forçado no Login...")
        await btn_entrar.dispatch_event("click")
        
        await page.wait_for_selector('a[href="#Discador_AutomáticoCollapse"]', state='visible', timeout=45000)
        
        print(f"[{server_name}] ✅ Login realizado!")
        return context, page, browser 

    except Exception as e:
        print(f"[{server_name}] ❌ Falha técnica: {e}")
        if browser: await browser.close()
        return None, None, None

class LoginManager:
    async def get_active_session(self, server: str) -> dict:
        server_name = get_server_name(server)
        print(f"[{server_name}] 🔑 Capturando sessão ativa...")
        async with async_playwright() as p:
            context, page, browser = await create_context_and_login(p, server)
            if not context: return {}
            browser_cookies = await context.cookies()
            await browser.close()
            session_dict = {}
            for cookie in browser_cookies:
                if cookie['name'] == 'PHPSESSID':
                    session_dict['PHPSESSID'] = cookie['value']
            return session_dict








