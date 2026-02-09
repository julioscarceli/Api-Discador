import os
import re
import json
import asyncio
import httpx
import redis
from typing import Dict, Any
from datetime import datetime, timedelta
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

# --- Configurações ---
URL_LOGIN = "http://187.60.56.102:8080/SipPulsePortal/pages/login/login.jsf"
USUARIO = os.getenv("NEXT_ROUTER_USER", "99971111225@sip2.v01p.com.br")
SENHA = os.getenv("NEXT_ROUTER_PASS", "jLEf2LMG8X9t8P7P")
API_URL_INTERNA = "https://api-discador-production.up.railway.app/api/atualizar-custos"

REDIS_URL = os.getenv("REDIS_URL", "redis://default:BMetYritSRFXIbozyBtCQpJpQKOxnnZE@redis.railway.internal:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

def formatar_valor_voip(texto):
    if not texto: return 0.0
    try:
        limpo = texto.strip().replace('.', '').replace(',', '.')
        return round(float(limpo), 2)
    except: return 0.0

def processar_dados_para_dashboard_formatado(d: Dict[str, Any]) -> Dict[str, Any]:
    saldo = f"R$ {d.get('saldo_atual', 0):.2f}".replace('.', ',')
    custo = f"R$ {d.get('custo_diario_total', 0):.2f}".replace('.', ',')
    custo_semanal = f"R$ {d.get('custo_semanal_acumulado', 0):.2f}".replace('.', ',')
    return {
        "saldo_atual": saldo, "custo_diario": custo, "custo_semanal": custo_semanal,
        "data_coleta": datetime.now().isoformat()
    }

async def coletar_custos_async(headless: bool = True) -> Dict[str, Any]:
    browser = None
    try:
        print(f"[WORKER] 🟢 Iniciando Scraping SipPulse (Headless: {headless})...", flush=True)
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless, 
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            )
            # Criamos um contexto com viewport maior para garantir que tudo renderize
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # 1. LOGIN
            print(f"[WORKER] 🌐 Acessando Portal...", flush=True)
            await page.goto(URL_LOGIN, wait_until="load", timeout=90000)
            
            await page.locator('input[id*="login"]').fill(USUARIO)
            await page.locator('input[id*="password"]').fill(SENHA)
            
            print("[WORKER] 🔑 Realizando login...", flush=True)
            await page.locator('input[value="Acessar Portal"]').click()
            
            # ESPERA CRÍTICA: Aguardamos a URL mudar ou estabilizar
            await page.wait_for_load_state("networkidle", timeout=60000)
            
            # SIMULAÇÃO HUMANA: Movemos o mouse e damos um scroll leve
            await page.mouse.move(100, 100)
            await page.mouse.wheel(0, 300)
            await page.wait_for_timeout(5000)

            # 2. EXTRAÇÃO DO SALDO (Tenta localizar pelo texto 'Crédito' se o seletor falhar)
            print("[WORKER] 💰 Localizando Saldo...", flush=True)
            saldo_raw = ""
            try:
                # Tenta localizar o elemento que contém o texto de valor numérico próximo ao saldo
                saldo_locator = page.locator("span.textoCredit")
                await saldo_locator.wait_for(state="attached", timeout=30000)
                saldo_raw = await saldo_locator.first.inner_text()
            except:
                print("[WORKER] ⚠️ Fallback: Buscando saldo por conteúdo de texto...", flush=True)
                # Busca qualquer span que tenha formato de moeda
                saldo_raw = await page.evaluate("() => document.querySelector('span.textoCredit')?.innerText || ''")

            if not saldo_raw:
                raise Exception("Não foi possível localizar o saldo na página pós-login.")

            saldo_final = formatar_valor_voip(saldo_raw)
            print(f"[WORKER] ✅ Saldo extraído: {saldo_final}", flush=True)

            # 3. NAVEGAÇÃO E CONSUMO
            print("[WORKER] 📂 Gerando Relatório de Consumo...", flush=True)
            await page.get_by_text("Chamadas Saintes").click()
            await page.wait_for_load_state("networkidle")
            await page.locator('input[value="Gerar Relatório"]').click()
            
            # XPath do rodapé validado
            consumo_xpath = "//tfoot//td[contains(@id, 'listCdrsTotal')][3]"
            await page.wait_for_selector(f"xpath={consumo_xpath}", state="attached", timeout=60000)
            await asyncio.sleep(8) # Tempo maior para o Railway processar o AJAX

            consumo_raw = await page.locator(f"xpath={consumo_xpath}").inner_text()
            custo_diario = formatar_valor_voip(consumo_raw)
            print(f"[WORKER] ✅ Consumo diário: {custo_diario}", flush=True)

            # LÓGICA REDIS
            hoje_str = datetime.now().strftime('%Y-%m-%d')
            r.set(f"custo_hist_{hoje_str}", str(custo_diario), ex=691200)

            return {
                "saldo_atual": saldo_final,
                "custo_diario_total": custo_diario,
                "custo_semanal_acumulado": 0.0 
            }
            
    except Exception as e:
        print(f"[WORKER-ERROR] ❌ Erro: {str(e)}", flush=True)
        return {"erro": str(e)}
    finally:
        if browser: await browser.close()

# ... (Mantenha o resto do arquivo como está)




















