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

# Configuração do Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://default:BMetYritSRFXIbozyBtCQpJpQKOxnnZE@redis.railway.internal:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

# --- FUNÇÕES DE APOIO E FORMATAÇÃO ---

def formatar_valor_voip(texto):
    """Converte '1.119,60750' para float 1119.61."""
    if not texto: return 0.0
    try:
        limpo = texto.strip().replace('.', '').replace(',', '.')
        return round(float(limpo), 2)
    except:
        return 0.0

def processar_dados_para_dashboard_formatado(d: Dict[str, Any]) -> Dict[str, Any]:
    """Prepara os dados para o Dashboard (Essencial para o api_server.py)."""
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
    """Envia os dados coletados para o Gateway."""
    print(f"[WORKER-API] 📡 Enviando para Gateway...", flush=True)
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(API_URL_INTERNA, json=dados, timeout=20.0)
            print(f"✅ [WORKER-API] Status: {resp.status_code}", flush=True)
        except Exception as e:
            print(f"❌ [WORKER-API] Falha de conexão: {e}", flush=True)

# --- MOTOR DE SCRAPING ---

async def coletar_custos_async(headless: bool = True) -> Dict[str, Any]:
    """Realiza o scraping no SipPulse com alta resiliência."""
    browser = None
    try:
        print(f"[WORKER] 🟢 Playwright iniciado (Headless: {headless})...", flush=True)
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless, 
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                ignore_https_errors=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # 1. LOGIN
            print(f"[WORKER] 🌐 Acessando Portal...", flush=True)
            await page.goto(URL_LOGIN, wait_until="load", timeout=90000)
            await page.locator('input[id*="login"]').fill(USUARIO)
            await page.locator('input[id*="password"]').fill(SENHA)
            
            print("[WORKER] 🔑 Realizando login...", flush=True)
            await page.locator('input[value="Acessar Portal"]').click()
            
            # Networkidle garante que o AJAX do JSF terminou de carregar o saldo
            await page.wait_for_load_state("networkidle", timeout=60000)
            await page.wait_for_timeout(5000) 

            # 2. SALDO
            print("[WORKER] 💰 Extraindo Saldo...", flush=True)
            saldo_raw = await page.locator("span.textoCredit").first.inner_text()
            saldo_final = formatar_valor_voip(saldo_raw)
            print(f"✅ Saldo Extraído: {saldo_final}", flush=True)

            # 3. CONSUMO
            print("[WORKER] 📂 Navegando para 'Chamadas Saintes'...", flush=True)
            await page.get_by_text("Chamadas Saintes").click()
            await page.wait_for_load_state("networkidle")
            
            print("[WORKER] 📊 Gerando Relatório...", flush=True)
            await page.locator('input[value="Gerar Relatório"]').click()
            
            xpath_total = "/html/body/table/tbody/tr[4]/td/table/tbody/tr/td[2]/form/table/tbody/tr[2]/td/table/tbody/tr/td/table[2]/tfoot/tr/td[3]"
            await page.wait_for_selector(f"xpath={xpath_total}", state="visible", timeout=60000)
            await asyncio.sleep(4) 
            
            consumo_raw = await page.locator(f"xpath={xpath_total}").inner_text()
            custo_diario = formatar_valor_voip(consumo_raw)
            print(f"✅ Consumo Extraído: {custo_diario}", flush=True)

            # --- LÓGICA REDIS: HISTÓRICO SEMANAL ---
            hoje_str = datetime.now().strftime('%Y-%m-%d')
            r.set(f"custo_hist_{hoje_str}", str(custo_diario), ex=691200)

            total_semanal = 0.0
            dias_desde_segunda = datetime.now().weekday() 
            for i in range(dias_desde_segunda + 1):
                data_busca = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                val = r.get(f"custo_hist_{data_busca}")
                if val: total_semanal += float(val)

            return {
                "saldo_atual": saldo_final,
                "custo_diario_total": custo_diario,
                "custo_semanal_acumulado": total_semanal 
            }
            
    except Exception as e:
        print(f"❌ Erro Crítico no Scraping: {e}", flush=True)
        return {"erro": str(e)}
    finally:
        if browser: await browser.close()

if __name__ == '__main__':
    print(f"--- [WORKER START] {datetime.now().strftime('%d/%m %H:%M:%S')} ---", flush=True)
    
    try:
        dados_brutos = asyncio.run(coletar_custos_async(headless=True))
        
        if not dados_brutos.get('erro'):
            # Envia para API Gateway salvar no Redis central
            asyncio.run(enviar_para_api(dados_brutos)) 
            
            # Log de confirmação com formatação local
            fmt = processar_dados_para_dashboard_formatado(dados_brutos)
            print(f"--- [FINISH] Saldo: {fmt['saldo_atual']} | Diário: {fmt['custo_diario']} ---", flush=True)
            
    except Exception as e:
        print(f"❌ Falha fatal no monitor: {e}", flush=True)
























