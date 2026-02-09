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
        limpo = texto.strip().replace('.', '').replace(',', '.')
        return round(float(limpo), 2)
    except: return 0.0

def processar_dados_para_dashboard_formatado(d: Dict[str, Any]) -> Dict[str, Any]:
    saldo = f"R$ {d.get('saldo_atual', 0):.2f}".replace('.', ',')
    custo = f"R$ {d.get('custo_diario_total', 0):.2f}".replace('.', ',')
    custo_semanal = f"R$ {d.get('custo_semanal_acumulado', 0):.2f}".replace('.', ',')
    return {"saldo_atual": saldo, "custo_diario": custo, "custo_semanal": custo_semanal, "data_coleta": datetime.now().isoformat()}

async def coletar_custos_async(headless: bool = True) -> Dict[str, Any]:
    browser = None
    try:
        print(f"[WORKER] 🟢 Iniciando Coleta SipPulse (Headless: {headless})...", flush=True)
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless, 
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                ignore_https_errors=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # 1. LOGIN RESILIENTE
            print(f"[WORKER] 🌐 Acessando Portal...", flush=True)
            await page.goto(URL_LOGIN, wait_until="load", timeout=90000)
            
            await page.locator('//*[@id="j_id27:login"]').fill(USUARIO)
            await page.locator('//*[@id="j_id27:password"]').fill(SENHA)
            
            print("[WORKER] 🔑 Disparando Login e aguardando navegação...", flush=True)
            # No Railway, aguardamos o evento de navegação explicitamente para garantir a troca de página
            async with page.expect_navigation(wait_until="networkidle", timeout=60000):
                await page.locator('input[value="Acessar Portal"]').click()

            # 2. CAPTURA DO SALDO (MODO FORCE)
            print("[WORKER] 💰 Localizando Saldo...", flush=True)
            # Pausa para o JSF estabilizar os componentes da tela
            await page.wait_for_timeout(10000) 
            
            saldo_raw = ""
            try:
                # Tenta esperar o seletor visual
                await page.wait_for_selector("span.textoCredit", state="attached", timeout=30000)
                saldo_raw = await page.locator("span.textoCredit").first.inner_text()
            except:
                print("[WORKER] ⚠️ Timeout visual. Tentando extração direta via DOM...", flush=True)
                # Se o Playwright não "vê" o elemento, tentamos extrair o texto via JavaScript puro
                saldo_raw = await page.evaluate("() => document.querySelector('.textoCredit')?.innerText || ''")

            if not saldo_raw or "," not in saldo_raw:
                print(f"[WORKER] ❌ Falha crítica: Saldo não encontrado ou inválido. Conteúdo: {saldo_raw}", flush=True)
                raise Exception("Saldo não localizado no Dashboard.")

            saldo_final = formatar_valor_voip(saldo_raw)
            print(f"💰 Saldo Extraído: R$ {saldo_final}", flush=True)

            # 3. RELATÓRIO DE CONSUMO
            print("📂 Navegando para 'Chamadas Saintes'...", flush=True)
            await page.get_by_text("Chamadas Saintes").click()
            await page.wait_for_load_state("networkidle", timeout=30000)

            print("📊 Gerando Relatório...", flush=True)
            await page.locator('input[value="Gerar Relatório"]').click()

            consumo_xpath = "/html/body/table/tbody/tr[4]/td/table/tbody/tr/td[2]/form/table/tbody/tr[2]/td/table/tbody/tr/td/table[2]/tfoot/tr/td[3]"
            await page.wait_for_selector(f"xpath={consumo_xpath}", state="attached", timeout=60000)
            
            # Pausa técnica validada localmente
            await asyncio.sleep(5)

            consumo_raw = await page.locator(f"xpath={consumo_xpath}").inner_text()
            print(f"🔍 Consumo Bruto: {consumo_raw}", flush=True)
            custo_diario = formatar_valor_voip(consumo_raw)

            # --- LÓGICA REDIS ---
            hoje_str = datetime.now().strftime('%Y-%m-%d')
            r.set(f"custo_hist_{hoje_str}", str(custo_diario), ex=691200)

            total_semanal = 0.0
            dias_desde_segunda = datetime.now().weekday() 
            for i in range(dias_desde_segunda + 1):
                data_busca = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                val = r.get(f"custo_hist_{data_busca}")
                if val: total_semanal += float(val)

            return {"saldo_atual": saldo_final, "custo_diario_total": custo_diario, "custo_semanal_acumulado": total_semanal}
            
    except Exception as e:
        print(f"❌ Erro Crítico: {e}", flush=True)
        return {"erro": str(e)}
    finally:
        if browser: await browser.close()

# ... (Mantenha as funções enviar_para_api e o bloco __main__ como no script anterior)






















