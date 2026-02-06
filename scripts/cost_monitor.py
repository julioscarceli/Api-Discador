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

# --- Configurações do Novo VOIP ---
URL_LOGIN = "http://187.60.56.102:8080/SipPulsePortal/pages/login/login.jsf"
USUARIO = os.getenv("NEXT_ROUTER_USER", "99971111225@sip2.v01p.com.br")
SENHA = os.getenv("NEXT_ROUTER_PASS", "jLEf2LMG8X9t8P7P")
API_URL_INTERNA = "https://api-discador-production.up.railway.app/api/atualizar-custos"

# Configuração do Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://default:BMetYritSRFXIbozyBtCQpJpQKOxnnZE@redis.railway.internal:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

def formatar_valor_voip(texto):
    """Formata '1.119,60750' para float 1119.60 validados localmente."""
    if not texto: return 0.0
    try:
        limpo = texto.strip().replace('.', '').replace(',', '.')
        return round(float(limpo), 2)
    except:
        return 0.0

def processar_dados_para_dashboard_formatado(d: Dict[str, Any]) -> Dict[str, Any]:
    """Formata os dados para exibição no Dashboard (R$ 0,00)."""
    saldo = f"R$ {d.get('saldo_atual', 0):.2f}".replace('.', ',')
    custo = f"R$ {d.get('custo_diario_total', 0):.2f}".replace('.', ',')
    custo_semanal = f"R$ {d.get('custo_semanal_acumulado', 0):.2f}".replace('.', ',')

    return {
        "saldo_atual": saldo,
        "custo_diario": custo,
        "custo_semanal": custo_semanal,
        "data_coleta": datetime.now().isoformat()
    }

async def coletar_custos_async(headless: bool = True) -> Dict[str, Any]:
    """Realiza o scraping no SipPulse em modo Headless."""
    browser = None
    try:
        print(f"[WORKER] 🟢 Iniciando Scraping SipPulse (Headless: {headless})...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless, 
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(ignore_https_errors=True)
            page = await context.new_page()

            # 1. LOGIN
            await page.goto(URL_LOGIN, wait_until="networkidle", timeout=60000)
            await page.locator('//*[@id="j_id27:login"]').fill(USUARIO)
            await page.locator('//*[@id="j_id27:password"]').fill(SENHA)
            await page.locator('input[value="Acessar Portal"]').click()
            await page.wait_for_load_state("networkidle")

            # 2. SALDO
            saldo_el = page.locator('span.textoCredit').first
            await saldo_el.wait_for(state="visible", timeout=20000)
            saldo_raw = await saldo_el.inner_text()
            saldo_final = formatar_valor_voip(saldo_raw)
            print(f"[WORKER] ✅ Saldo extraído: {saldo_final}")

            # 3. CONSUMO (NAVEGAÇÃO RELATÓRIO)
            await page.locator('//*[@id="iconfrmMenu:j_id50"]').click()
            await page.wait_for_load_state("networkidle")
            await page.locator('input[value="Gerar Relatório"]').click()
            
            # Seletor Full XPath validado localmente
            consumo_xpath = "/html/body/table/tbody/tr[4]/td/table/tbody/tr/td[2]/form/table/tbody/tr[2]/td/table/tbody/tr/td/table[2]/tfoot/tr/td[3]"
            await page.wait_for_selector(f"xpath={consumo_xpath}", state="visible", timeout=45000)
            await asyncio.sleep(3) # Pausa técnica JSF
            
            consumo_raw = await page.locator(f"xpath={consumo_xpath}").inner_text()
            custo_diario = formatar_valor_voip(consumo_raw)
            print(f"[WORKER] ✅ Consumo diário extraído: {custo_diario}")

            # --- LÓGICA REDIS: ACUMULADO SEMANAL ---
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
                "custo_semanal_acumulado": total_semanal 
            }
            
    except Exception as e:
        print(f"[WORKER-ERROR] ❌ Falha: {str(e)}")
        return {"erro": str(e)}
    finally:
        if browser: await browser.close()

async def enviar_para_api(dados: Dict[str, Any]):
    """Envia os resultados para o api_server renderizar no front."""
    print(f"[WORKER-API] 📡 Enviando para Gateway...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(API_URL_INTERNA, json=dados, timeout=20.0)
            print(f"✅ [WORKER-API] Status: {resp.status_code}")
        except Exception as e:
            print(f"❌ [WORKER-API] Falha de conexão: {e}")

if __name__ == '__main__':
    print(f"--- [WORKER START] {datetime.now().strftime('%d/%m %H:%M:%S')} ---")
    # No Railway roda em headless=True por padrão
    dados_brutos = asyncio.run(coletar_custos_async(headless=True))
    
    if not dados_brutos.get('erro'):
        asyncio.run(enviar_para_api(dados_brutos)) 
        fmt = processar_dados_para_dashboard_formatado(dados_brutos)
        print(f"--- [FINISH] Saldo: {fmt['saldo_atual']} | Diário: {fmt['custo_diario']} ---")










