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

def formatar_valor_voip(texto):
    """Formata valores como '1.201,55750' para float 1201.56."""
    if not texto: return 0.0
    try:
        limpo = texto.strip().replace('.', '').replace(',', '.')
        return round(float(limpo), 2)
    except: return 0.0

def processar_dados_para_dashboard_formatado(d: Dict[str, Any]) -> Dict[str, Any]:
    """Prepara os dados no formato R$ 0,00 para o front-end."""
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
    browser = None
    try:
        print(f"[WORKER] 🟢 Iniciando Scraping SipPulse (Headless: {headless})...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless, 
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            context = await browser.new_context(
                ignore_https_errors=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # 1. LOGIN
            print(f"[WORKER] 🌐 Acessando Portal: {URL_LOGIN}")
            await page.goto(URL_LOGIN, wait_until="domcontentloaded", timeout=90000)
            
            await page.locator('input[id*="login"]').fill(USUARIO)
            await page.locator('input[id*="password"]').fill(SENHA)
            
            print("[WORKER] 🔑 Realizando login...")
            # Clicamos e esperamos a carga da página, mas sem depender de navegação estrita
            await page.locator('input[value="Acessar Portal"]').click()
            
            # Espera forçada para renderização do dashboard JSF no Railway
            await page.wait_for_timeout(10000) 

            # 2. EXTRAÇÃO DO SALDO (Tenta múltiplos seletores)
            print("[WORKER] 💰 Extraindo Saldo...")
            saldo_raw = ""
            try:
                # Seletor por classe CSS
                await page.wait_for_selector("span.textoCredit", state="visible", timeout=45000)
                saldo_raw = await page.locator("span.textoCredit").first.inner_text()
            except:
                print("[WORKER] ⚠️ CSS falhou, tentando seletor de ID parcial...")
                await page.wait_for_selector('span[id*="panelPersonInfo"]', state="visible", timeout=20000)
                saldo_raw = await page.locator('span[id*="panelPersonInfo"]').first.inner_text()

            saldo_final = formatar_valor_voip(saldo_raw)
            print(f"[WORKER] ✅ Saldo extraído: {saldo_final}")

            # 3. NAVEGAÇÃO E CONSUMO
            print("[WORKER] 📂 Gerando Relatório de Consumo...")
            # Usa o texto do menu para clicar
            await page.get_by_text("Chamadas Saintes").click()
            await page.wait_for_timeout(5000)
            
            await page.locator('input[value="Gerar Relatório"]').click()
            
            # XPath do rodapé validado localmente
            consumo_xpath = "/html/body/table/tbody/tr[4]/td/table/tbody/tr/td[2]/form/table/tbody/tr[2]/td/table/tbody/tr/td/table[2]/tfoot/tr/td[3]"
            
            await page.wait_for_selector(f"xpath={consumo_xpath}", state="attached", timeout=60000)
            await asyncio.sleep(5) # Pausa técnica robusta para processamento de tabela

            consumo_raw = await page.locator(f"xpath={consumo_xpath}").inner_text()
            custo_diario = formatar_valor_voip(consumo_raw)
            print(f"[WORKER] ✅ Consumo diário extraído: {custo_diario}")

            # LÓGICA REDIS
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
        print(f"[WORKER-ERROR] ❌ Erro: {str(e)}")
        return {"erro": str(e)}
    finally:
        if browser: await browser.close()

async def enviar_para_api(dados: Dict[str, Any]):
    """Envia os dados para a API Gateway."""
    print(f"[WORKER-API] 📡 Enviando para Gateway...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(API_URL_INTERNA, json=dados, timeout=20.0)
            print(f"✅ [WORKER-API] Status: {resp.status_code}")
        except Exception as e:
            print(f"❌ [WORKER-API] Falha de conexão: {e}")

if __name__ == '__main__':
    print(f"--- [WORKER START] {datetime.now().strftime('%d/%m %H:%M:%S')} ---")
    dados_brutos = asyncio.run(coletar_custos_async(headless=True))
    if not dados_brutos.get('erro'):
        asyncio.run(enviar_para_api(dados_brutos)) 
        fmt = processar_dados_para_dashboard_formatado(dados_brutos)
        print(f"--- [FINISH] Saldo: {fmt['saldo_atual']} | Diário: {fmt['custo_diario']} ---")

















