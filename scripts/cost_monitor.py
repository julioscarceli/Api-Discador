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

# --- FUNÇÕES DE APOIO ---

def formatar_valor_voip(texto):
    """Formata valores como '12.021,25' para float 12021.25."""
    if not texto: return 0.0
    try:
        limpo = texto.strip().replace('.', '').replace(',', '.')
        return round(float(limpo), 2)
    except: return 0.0

def processar_dados_para_dashboard_formatado(d: Dict[str, Any]) -> Dict[str, Any]:
    """Formata para exibição no front-end."""
    saldo = f"R$ {d.get('saldo_atual', 0):.2f}".replace('.', ',')
    custo = f"R$ {d.get('custo_diario_total', 0):.2f}".replace('.', ',')
    custo_semanal = f"R$ {d.get('custo_semanal_acumulado', 0):.2f}".replace('.', ',')
    return {"saldo_atual": saldo, "custo_diario": custo, "custo_semanal": custo_semanal, "data_coleta": datetime.now().isoformat()}

async def enviar_para_api(dados: Dict[str, Any]):
    print(f"[WORKER-API] 📡 Enviando para Gateway...", flush=True)
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(API_URL_INTERNA, json=dados, timeout=20.0)
            print(f"✅ [WORKER-API] Status: {resp.status_code}", flush=True)
        except Exception as e:
            print(f"❌ [WORKER-API] Falha: {e}", flush=True)

# --- MOTOR DE SCRAPING ---

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
                viewport={'width': 1280, 'height': 800},
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
            
            # 2. CAPTURA DO SALDO (ESTRATÉGIA BASEADA NO PRINT)
            print("[WORKER] 💰 Localizando Saldo...", flush=True)
            # Networkidle é essencial para esperar o preenchimento da tabela
            await page.wait_for_load_state("networkidle", timeout=60000)
            
            # Segundo o print, o saldo está em uma tabela. Vamos buscar o texto "Créditos:"
            saldo_raw = ""
            try:
                # Localizamos a célula que vem logo após o texto "Créditos:"
                # O SipPulse usa tabelas JSF onde o valor fica em um span ou td vizinho
                await page.wait_for_selector("text=Créditos:", state="visible", timeout=30000)
                
                # Extração via JavaScript para garantir que pegamos o valor numérico ao lado do label
                saldo_raw = await page.evaluate("""() => {
                    const labels = Array.from(document.querySelectorAll('td, span, label'));
                    const creditLabel = labels.find(el => el.innerText.includes('Créditos:'));
                    if (creditLabel) {
                        // Tenta pegar o próximo elemento ou o texto numérico na mesma linha
                        return creditLabel.parentElement.innerText.replace('Créditos:', '').trim();
                    }
                    return document.querySelector('.textoCredit')?.innerText || '';
                }""")
            except:
                print("[WORKER] ⚠️ Fallback visual...", flush=True)
                saldo_raw = await page.locator("span.textoCredit").first.inner_text()

            if not saldo_raw or "," not in saldo_raw:
                raise Exception(f"Saldo inválido capturado: {saldo_raw}")

            saldo_final = formatar_valor_voip(saldo_raw)
            print(f"✅ Saldo Extraído: {saldo_final}", flush=True)

            # 3. NAVEGAÇÃO PARA RELATÓRIO (Chamadas Saintes)
            print("[WORKER] 📂 Navegando para 'Chamadas Saintes'...", flush=True)
            await page.get_by_text("Chamadas Saintes").click()
            await page.wait_for_load_state("networkidle")
            
            print("[WORKER] 📊 Gerando Relatório...", flush=True)
            await page.locator('input[value="Gerar Relatório"]').click()
            
            # XPath validado no seu debug local
            xpath_total = "/html/body/table/tbody/tr[4]/td/table/tbody/tr/td[2]/form/table/tbody/tr[2]/td/table/tbody/tr/td/table[2]/tfoot/tr/td[3]"
            await page.wait_for_selector(f"xpath={xpath_total}", state="attached", timeout=60000)
            await asyncio.sleep(5) 
            
            consumo_raw = await page.locator(f"xpath={xpath_total}").inner_text()
            custo_diario = formatar_valor_voip(consumo_raw)
            print(f"✅ Consumo Extraído: {custo_diario}", flush=True)

            # LÓGICA REDIS
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
        print(f"❌ Erro Crítico no Scraping: {e}", flush=True)
        return {"erro": str(e)}
    finally:
        if browser: await browser.close()

if __name__ == '__main__':
    print(f"--- [WORKER START] {datetime.now().strftime('%d/%m %H:%M:%S')} ---", flush=True)
    try:
        dados_brutos = asyncio.run(coletar_custos_async(headless=True))
        if not dados_brutos.get('erro'):
            asyncio.run(enviar_para_api(dados_brutos)) 
            fmt = processar_dados_para_dashboard_formatado(dados_brutos)
            print(f"--- [FINISH] Saldo: {fmt['saldo_atual']} | Diário: {fmt['custo_diario']} ---", flush=True)
    except Exception as e:
        print(f"❌ Falha fatal: {e}", flush=True)


























