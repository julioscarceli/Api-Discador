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

# --- CONFIGURATIONS ---
URL_LOGIN = "http://187.60.56.102:8080/SipPulsePortal/pages/login/login.jsf"
USUARIO = os.getenv("NEXT_ROUTER_USER", "99971111225@sip2.v01p.com.br")
SENHA = os.getenv("NEXT_ROUTER_PASS", "jLEf2LMG8X9t8P7P")
API_URL_INTERNA = "https://api-discador-production.up.railway.app/api/atualizar-custos"

# Redis Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://default:BMetYritSRFXIbozyBtCQpJpQKOxnnZE@redis.railway.internal:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

# --- SUPPORT & FORMATTING FUNCTIONS (REQUIRED BY API_SERVER) ---

def formatar_valor_voip(texto):
    """Converts '12.021,25' to float 12021.25."""
    if not texto: return 0.0
    try:
        limpo = texto.strip().replace('.', '').replace(',', '.')
        return round(float(limpo), 2)
    except:
        return 0.0

def processar_dados_para_dashboard_formatado(d: Dict[str, Any]) -> Dict[str, Any]:
    """Prepares raw data for the Dashboard display (Required by api_server.py)."""
    saldo = f"R$ {d.get('saldo_atual', 0):.2f}".replace('.', ',')
    custo = f"R$ {d.get('custo_diario_total', 0):.2f}".replace('.', ',')
    custo_semanal = f"R$ {d.get('custo_semanal_acumulado', 0):.2f}".replace('.', ',')

    return {
        "saldo_atual": saldo,
        "custo_diario": custo,
        "custo_semanal": custo_semanal,
        "data_coleta": datetime.now().isoformat()
    }

async def enviar_para_api(dados: Dict[str, Any]):
    """Sends collected data to the API Gateway."""
    print(f"[WORKER-API] 📡 Sending to Gateway...", flush=True)
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(API_URL_INTERNA, json=dados, timeout=20.0)
            print(f"✅ [WORKER-API] Status: {resp.status_code}", flush=True)
        except Exception as e:
            print(f"❌ [WORKER-API] Connection failed: {e}", flush=True)

# --- SCRAPING ENGINE ---

async def coletar_custos_async(headless: bool = True) -> Dict[str, Any]:
    """Scrapes SipPulse with high resilience for Railway environment."""
    browser = None
    try:
        print(f"[WORKER] 🟢 Playwright started (Headless: {headless})...", flush=True)
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless, 
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # 1. LOGIN
            print(f"[WORKER] 🌐 Accessing Portal...", flush=True)
            await page.goto(URL_LOGIN, wait_until="load", timeout=90000)
            await page.locator('input[id*="login"]').fill(USUARIO)
            await page.locator('input[id*="password"]').fill(SENHA)
            
            print("[WORKER] 🔑 Logging in...", flush=True)
            await page.locator('input[value="Acessar Portal"]').click()
            
            # Wait for JSF Dashboard to stabilize
            await page.wait_for_load_state("networkidle", timeout=60000)
            await page.wait_for_timeout(15000) 

            # 2. BALANCE EXTRACTION
            print("[WORKER] 💰 Extracting Balance...", flush=True)
            # Use JS Evaluation to bypass visibility issues in headless mode
            saldo_raw = await page.evaluate("() => document.querySelector('span.textoCredit')?.innerText")
            
            if not saldo_raw:
                # Fallback to absolute XPath if JS eval fails
                xpath_saldo = "/html/body/table/tbody/tr[4]/td/table/tbody/tr/td[2]/div/div/table/tbody/tr[1]/td[2]/span"
                saldo_raw = await page.locator(f"xpath={xpath_saldo}").inner_text()

            saldo_final = formatar_valor_voip(saldo_raw)
            print(f"✅ Balance Extracted: {saldo_final}", flush=True)

            # 3. CONSUMPTION
            print("[WORKER] 📂 Navigating to 'Chamadas Saintes'...", flush=True)
            await page.get_by_text("Chamadas Saintes").click()
            await page.wait_for_load_state("networkidle")
            await page.locator('input[value="Gerar Relatório"]').click()
            
            # XPath for footer total validated in local debug
            xpath_total = "/html/body/table/tbody/tr[4]/td/table/tbody/tr/td[2]/form/table/tbody/tr[2]/td/table/tbody/tr/td/table[2]/tfoot/tr/td[3]"
            await page.wait_for_selector(f"xpath={xpath_total}", state="attached", timeout=60000)
            await asyncio.sleep(5) 
            
            consumo_raw = await page.locator(f"xpath={xpath_total}").inner_text()
            custo_diario = formatar_valor_voip(consumo_raw)
            print(f"✅ Consumption Extracted: {custo_diario}", flush=True)

            # --- REDIS LOGIC: WEEKLY ACCUMULATED ---
            hoje = datetime.now()
            hoje_str = hoje.strftime('%Y-%m-%d')
            r.set(f"custo_hist_{hoje_str}", str(custo_diario), ex=691200)

            total_semanal = 0.0
            dias_desde_segunda = hoje.weekday() 
            for i in range(dias_desde_segunda + 1):
                data_busca = (hoje - timedelta(days=i)).strftime('%Y-%m-%d')
                val = r.get(f"custo_hist_{data_busca}")
                if val: total_semanal += float(val)

            return {
                "saldo_atual": saldo_final,
                "custo_diario_total": custo_diario,
                "custo
































