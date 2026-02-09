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

# --- CONFIGURAÇÕES ---
URL_LOGIN = "http://187.60.56.102:8080/SipPulsePortal/pages/login/login.jsf"
USUARIO = os.getenv("NEXT_ROUTER_USER", "99971111225@sip2.v01p.com.br")
SENHA = os.getenv("NEXT_ROUTER_PASS", "jLEf2LMG8X9t8P7P")
API_URL_INTERNA = "https://api-discador-production.up.railway.app/api/atualizar-custos"

REDIS_URL = os.getenv("REDIS_URL", "redis://default:BMetYritSRFXIbozyBtCQpJpQKOxnnZE@redis.railway.internal:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

def formatar_valor_voip(texto):
    if not texto: return 0.0
    try:
        # Lógica de limpeza baseada no print: 12.021,25 -> 12021.25
        limpo = texto.strip().replace('.', '').replace(',', '.')
        return round(float(limpo), 2)
    except: return 0.0

async def coletar_custos_async(headless: bool = True) -> Dict[str, Any]:
    browser = None
    try:
        print(f"[WORKER] 🟢 Inicializando Motor Playwright...", flush=True)
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless, 
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            )
            # Contexto com viewport idêntico ao de um desktop real
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # 1. ACESSO E LOGIN LENTO
            print(f"[WORKER] 🌐 Acessando Portal...", flush=True)
            await page.goto(URL_LOGIN, wait_until="load", timeout=90000)
            
            await page.locator('input[id*="login"]').fill(USUARIO)
            await page.wait_for_timeout(1000)
            await page.locator('input[id*="password"]').fill(SENHA)
            
            print("[WORKER] 🔑 Clicando em Login...", flush=True)
            # No Railway, clicamos e aguardamos 15s para estabilização forçada
            await page.locator('input[value="Acessar Portal"]').click()
            await page.wait_for_timeout(15000) 

            # 2. CAPTURA DO SALDO (VIA DOM DIRETO)
            # Tentamos capturar o saldo usando o Full XPath absoluto enviado por você
            print("[WORKER] 💰 Extraindo Saldo...", flush=True)
            xpath_saldo = "/html/body/table/tbody/tr[4]/td/table/tbody/tr/td[2]/div/div/table/tbody/tr[1]/td[2]/span"
            
            # Tenta 3 vezes antes de desistir
            saldo_raw = ""
            for i in range(3):
                try:
                    el = page.locator(f"xpath={xpath_saldo}")
                    if await el.count() > 0:
                        saldo_raw = await el.inner_text()
                        break
                except:
                    await page.wait_for_timeout(5000)
            
            if not saldo_raw:
                # Fallback para o seletor de classe visual
                saldo_raw = await page.evaluate("() => document.querySelector('.textoCredit')?.innerText")

            saldo_final = formatar_valor_voip(saldo_raw)
            print(f"✅ Saldo: {saldo_final}", flush=True)

            # 3. NAVEGAÇÃO E RELATÓRIO
            print("[WORKER] 📂 Gerando Relatório...", flush=True)
            # Clica no item do menu lateral conforme o print
            await page.get_by_text("Chamadas Saintes").click()
            await page.wait_for_timeout(5000)
            
            await page.locator('input[value="Gerar Relatório"]').click()
            
            # XPath do rodapé (Total) validado localmente
            xpath_total = "/html/body/table/tbody/tr[4]/td/table/tbody/tr/td[2]/form/table/tbody/tr[2]/td/table/tbody/tr/td/table[2]/tfoot/tr/td[3]"
            await page.wait_for_selector(f"xpath={xpath_total}", state="attached", timeout=60000)
            await asyncio.sleep(5) 
            
            consumo_raw = await page.locator(f"xpath={xpath_total}").inner_text()
            custo_diario = formatar_valor_voip(consumo_raw)
            print(f"✅ Consumo: {custo_diario}", flush=True)

            # --- ENVIO E REDIS ---
            hoje_str = datetime.now().strftime('%Y-%m-%d')
            r.set(f"custo_hist_{hoje_str}", str(custo_diario), ex=691200)

            return {"saldo_atual": saldo_final, "custo_diario_total": custo_diario, "custo_semanal_acumulado": 0.0}
            
    except Exception as e:
        print(f"[WORKER-ERROR] ❌ Falha: {str(e)}", flush=True)
        return {"erro": str(e)}
    finally:
        if browser: await browser.close()

# ... (Manter funções de formatação e main como antes)































