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

async def coletar_custos_async(headless: bool = True) -> Dict[str, Any]:
    browser = None
    try:
        print(f"[WORKER] 🟢 Iniciando Scraping SipPulse (Headless: {headless})...")
        async with async_playwright() as p:
            # Aumentamos a resiliência do navegador para ambientes Linux/Railway
            browser = await p.chromium.launch(
                headless=headless, 
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-setuid-sandbox"]
            )
            context = await browser.new_context(
                ignore_https_errors=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # 1. LOGIN
            print(f"[WORKER] 🌐 Acessando Portal: {URL_LOGIN}")
            await page.goto(URL_LOGIN, wait_until="load", timeout=90000)
            
            # Preenchimento com pequenos delays para simular humano
            await page.locator('//*[@id="j_id27:login"]').fill(USUARIO)
            await page.locator('//*[@id="j_id27:password"]').fill(SENHA)
            
            # Clicamos e esperamos a navegação ser confirmada pelo servidor
            print("[WORKER] 🔑 Realizando login...")
            await asyncio.gather(
                page.wait_for_navigation(wait_until="networkidle", timeout=60000),
                page.locator('input[value="Acessar Portal"]').click()
            )

            # 2. EXTRAÇÃO DO SALDO
            print("[WORKER] 💰 Localizando Saldo...")
            # Tentativa de localizar o elemento com espera inteligente de estabilidade
            saldo_selector = "span.textoCredit"
            
            # Forçamos uma espera curta para o JSF processar o AJAX inicial
            await page.wait_for_timeout(5000) 
            
            # Se o span.textoCredit falhar, tentamos o XPath absoluto
            try:
                await page.wait_for_selector(saldo_selector, state="visible", timeout=30000)
            except:
                print("[WORKER] ⚠️ Seletor CSS falhou, tentando XPath absoluto...")
                saldo_selector = 'xpath=//*[@id="panelPersonInfo_body"]/table/tbody/tr[1]/td[2]/span'
                await page.wait_for_selector(saldo_selector, state="visible", timeout=30000)

            saldo_raw = await page.locator(saldo_selector).first.inner_text()
            saldo_final = formatar_valor_voip(saldo_raw)
            print(f"[WORKER] ✅ Saldo extraído: {saldo_final}")

            # 3. NAVEGAÇÃO E CONSUMO
            print("[WORKER] 📂 Gerando Relatório de Consumo...")
            await page.locator('//*[@id="iconfrmMenu:j_id50"]').click()
            await page.wait_for_load_state("networkidle")
            
            await page.locator('input[value="Gerar Relatório"]').click()
            
            # XPath do rodapé validado localmente
            consumo_xpath = "/html/body/table/tbody/tr[4]/td/table/tbody/tr/td[2]/form/table/tbody/tr[2]/td/table/tbody/tr/td/table[2]/tfoot/tr/td[3]"
            
            await page.wait_for_selector(f"xpath={consumo_xpath}", state="visible", timeout=60000)
            await asyncio.sleep(3) 
            
            consumo_raw = await page.locator(f"xpath={consumo_xpath}").inner_text()
            custo_diario = formatar_valor_voip(consumo_raw)
            print(f"[WORKER] ✅ Consumo diário: {custo_diario}")

            # Lógica de Redis (MANTIDA)
            hoje_str = datetime.now().strftime('%Y-%m-%d')
            r.set(f"custo_hist_{hoje_str}", str(custo_diario), ex=691200)

            return {
                "saldo_atual": saldo_final,
                "custo_diario_total": custo_diario,
                "custo_semanal_acumulado": 0.0 # Calculado no dashboard
            }
            
    except Exception as e:
        print(f"[WORKER-ERROR] ❌ Erro: {str(e)}")
        return {"erro": str(e)}
    finally:
        if browser: await browser.close()

# ... (Manter o restante das funções enviar_para_api e main)

# ... (Manter o restante das funções enviar_para_api e main)

async def enviar_para_api(dados: Dict[str, Any]):
    """Envia os dados para a API Gateway atualizar o dashboard."""
    print(f"[WORKER-API] 📡 Enviando dados para Gateway...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(API_URL_INTERNA, json=dados, timeout=20.0)
            if resp.status_code == 200:
                print("✅ [WORKER-API] Atualização confirmada pelo Gateway.")
            else:
                print(f"❌ [WORKER-API] Erro na API: {resp.status_code}")
        except Exception as e:
            print(f"❌ [WORKER-API] Falha de conexão: {e}")

if __name__ == '__main__':
    print(f"--- [WORKER START] {datetime.now().strftime('%d/%m %H:%M:%S')} ---")
    # Executa em modo Headless no Railway
    dados_brutos = asyncio.run(coletar_custos_async(headless=True))
    
    if not dados_brutos.get('erro'):
        asyncio.run(enviar_para_api(dados_brutos)) 
        fmt = processar_dados_para_dashboard_formatado(dados_brutos)
        print(f"--- [WORKER FINISH] Saldo: {fmt['saldo_atual']} | Diário: {fmt['custo_diario']} ---")













