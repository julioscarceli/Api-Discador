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

            # 1. LOGIN COM ESPERA REFORÇADA
            print(f"[WORKER] 🌐 Acessando Portal: {URL_LOGIN}")
            await page.goto(URL_LOGIN, wait_until="load", timeout=90000)
            
            await page.locator('input[id*="login"]').fill(USUARIO)
            await page.locator('input[id*="password"]').fill(SENHA)
            
            print("[WORKER] 🔑 Realizando login...")
            # No Railway, forçamos a espera pela URL mudar ou o seletor interno aparecer
            await page.locator('input[value="Acessar Portal"]').click()
            
            # 2. ESPERA PELO DASHBOARD (ESTRATÉGIA DE RETRY)
            print("[WORKER] 💰 Aguardando Dashboard...")
            # Em vez de apenas um seletor, esperamos o carregamento completo da página
            await page.wait_for_load_state("networkidle", timeout=60000)
            
            # Seletor de Saldo com múltiplas tentativas (CSS e Texto)
            saldo_raw = ""
            try:
                # Tenta localizar por texto que contenha o prefixo de saldo ou classe conhecida
                # O SipPulse costuma renderizar o saldo dentro de um painel de informações pessoais
                saldo_locator = page.get_by_text(re.compile(r'\d+,\d+')).first
                await saldo_locator.wait_for(state="visible", timeout=30000)
                saldo_raw = await saldo_locator.inner_text()
            except:
                print("[WORKER] ⚠️ Busca por texto falhou, tentando seletor fallback...")
                # Fallback para o seletor capturado no log
                await page.wait_for_selector("span.textoCredit", state="visible", timeout=30000)
                saldo_raw = await page.locator("span.textoCredit").first.inner_text()

            saldo_final = formatar_valor_voip(saldo_raw)
            print(f"[WORKER] ✅ Saldo extraído: {saldo_final}")

            # 3. NAVEGAÇÃO E RELATÓRIO
            print("[WORKER] 📂 Gerando Relatório de Consumo...")
            await page.get_by_text("Chamadas Saintes").click()
            await page.wait_for_load_state("networkidle")
            
            await page.locator('input[value="Gerar Relatório"]').click()
            
            # XPath validado localmente
            consumo_xpath = "/html/body/table/tbody/tr[4]/td/table/tbody/tr/td[2]/form/table/tbody/tr[2]/td/table/tbody/tr/td/table[2]/tfoot/tr/td[3]"
            
            await page.wait_for_selector(f"xpath={consumo_xpath}", state="attached", timeout=60000)
            # Pausa técnica para garantir injeção de dados via AJAX
            await asyncio.sleep(7) 

            consumo_raw = await page.locator(f"xpath={consumo_xpath}").inner_text()
            custo_diario = formatar_valor_voip(consumo_raw)
            print(f"[WORKER] ✅ Consumo diário: {custo_diario}")

            # LÓGICA REDIS
            hoje_str = datetime.now().strftime('%Y-%m-%d')
            r.set(f"custo_hist_{hoje_str}", str(custo_diario), ex=691200)

            return {
                "saldo_atual": saldo_final,
                "custo_diario_total": custo_diario,
                "custo_semanal_acumulado": 0.0 # Calculado no dashboard
            }
            
    except Exception as e:
        print(f"[WORKER-ERROR] ❌ Erro Crítico: {str(e)}")
        return {"erro": str(e)}
    finally:
        if browser: await browser.close()

# ... (Manter funções enviar_para_api e main conforme implementado anteriormente)


















