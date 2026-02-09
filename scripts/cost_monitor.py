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

# --- CONFIGURAÇÕES DO PORTAL ---
URL_LOGIN = "http://187.60.56.102:8080/SipPulsePortal/pages/login/login.jsf"
USUARIO = os.getenv("NEXT_ROUTER_USER", "99971111225@sip2.v01p.com.br")
SENHA = os.getenv("NEXT_ROUTER_PASS", "jLEf2LMG8X9t8P7P")
API_URL_INTERNA = "https://api-discador-production.up.railway.app/api/atualizar-custos"

# Configuração do Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://default:BMetYritSRFXIbozyBtCQpJpQKOxnnZE@redis.railway.internal:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

def formatar_valor_voip(texto):
    """Formata '1.119,60750' para float 1119.60 (Lógica validada localmente)"""
    if not texto: return 0.0
    try:
        limpo = texto.strip().replace('.', '').replace(',', '.')
        return round(float(limpo), 2)
    except:
        return 0.0

def processar_dados_para_dashboard_formatado(d: Dict[str, Any]) -> Dict[str, Any]:
    """Formatação para o Front-end"""
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
            # Contexto com User Agent real para evitar bloqueios em Headless
            context = await browser.new_context(
                ignore_https_errors=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # 1. LOGIN (Copiado do seu debug local)
            print(f"[WORKER] 🌐 Acessando Portal...", flush=True)
            await page.goto(URL_LOGIN, wait_until="networkidle", timeout=60000)
            await page.locator('//*[@id="j_id27:login"]').fill(USUARIO)
            await page.locator('//*[@id="j_id27:password"]').fill(SENHA)
            await page.locator('input[value="Acessar Portal"]').click()
            await page.wait_for_load_state("networkidle")

            # 2. SALDO
            print("[WORKER] 💰 Extraindo Saldo...", flush=True)
            saldo_el = page.locator('span.textoCredit').first
            await saldo_el.wait_for(state="visible", timeout=45000)
            saldo_raw = await saldo_el.inner_text()
            saldo_final = formatar_valor_voip(saldo_raw)
            print(f"💰 Saldo Extraído: R$ {saldo_final}", flush=True)

            # 3. NAVEGAÇÃO PARA RELATÓRIO
            print("📂 Navegando para 'Chamadas Saintes'...", flush=True)
            await page.locator('//*[@id="iconfrmMenu:j_id50"]').click()
            await page.wait_for_load_state("networkidle")

            print("📊 Gerando Relatório...", flush=True)
            await page.locator('input[value="Gerar Relatório"]').click()

            # --- SELETOR DE CONSUMO (IDÊNTICO AO SEU DEBUG LOCAL) ---
            consumo_xpath = "/html/body/table/tbody/tr[4]/td/table/tbody/tr/td[2]/form/table/tbody/tr[2]/td/table/tbody/tr/td/table[2]/tfoot/tr/td[3]"
            await page.wait_for_selector(f"xpath={consumo_xpath}", state="visible", timeout=60000)
            
            # Pausa técnica validada localmente
            await asyncio.sleep(3)

            consumo_raw = await page.locator(f"xpath={consumo_xpath}").inner_text()
            print(f"🔍 Texto bruto capturado: {consumo_raw}", flush=True)
            custo_diario = formatar_valor_voip(consumo_raw)

            # --- LÓGICA REDIS (Acumulado Semanal) ---
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
        print(f"❌ Erro Crítico no Worker: {e}", flush=True)
        return {"erro": str(e)}
    finally:
        if browser: await browser.close()

async def enviar_para_api(dados: Dict[str, Any]):
    print(f"[WORKER-API] 📡 Enviando dados para Gateway...", flush=True)
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(API_URL_INTERNA, json=dados, timeout=20.0)
            print(f"✅ [WORKER-API] Status: {resp.status_code}", flush=True)
        except Exception as e:
            print(f"❌ [WORKER-API] Falha de conexão: {e}", flush=True)

if __name__ == '__main__':
    print(f"--- [WORKER START] {datetime.now().strftime('%d/%m %H:%M:%S')} ---", flush=True)
    dados_brutos = asyncio.run(coletar_custos_async(headless=True))
    if not dados_brutos.get('erro'):
        asyncio.run(enviar_para_api(dados_brutos)) 
        fmt = processar_dados_para_dashboard_formatado(dados_brutos)
        print(f"--- [FINISH] Saldo: {fmt['saldo_atual']} | Diário: {fmt['custo_diario']} ---", flush=True)





















