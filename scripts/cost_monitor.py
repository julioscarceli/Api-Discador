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
    """Formata valores como '12.021,25' para float 12021.25."""
    if not texto: return 0.0
    try:
        # Limpeza robusta: remove tudo que não é dígito, vírgula ou ponto
        limpo = re.sub(r'[^\d,.]', '', texto)
        # Se houver ponto e vírgula, remove o ponto (milhar) e troca vírgula por ponto (decimal)
        if '.' in limpo and ',' in limpo:
            limpo = limpo.replace('.', '').replace(',', '.')
        else:
            limpo = limpo.replace(',', '.')
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
                viewport={'width': 1366, 'height': 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # 1. LOGIN (Usando seletor de ID parcial para JSF)
            print(f"[WORKER] 🌐 Acessando Portal...", flush=True)
            await page.goto(URL_LOGIN, wait_until="load", timeout=90000)
            await page.locator('input[id*="login"]').fill(USUARIO)
            await page.locator('input[id*="password"]').fill(SENHA)
            
            print("[WORKER] 🔑 Realizando login...", flush=True)
            # Esperamos a navegação após o clique
            await asyncio.gather(
                page.wait_for_navigation(wait_until="networkidle", timeout=60000),
                page.locator('input[value="Acessar Portal"]').click(),
            )

            # 2. CAPTURA DO SALDO (ESTRATEGIA DE POSIÇÃO)
            print("[WORKER] 💰 Localizando Saldo...", flush=True)
            # Conforme o print, o saldo é o primeiro campo da tabela "Dados da Conta"
            # O ID do JSF geralmente contém 'panelPersonInfo'
            saldo_raw = ""
            try:
                # Tentativa 1: Localizar pelo texto vizinho "Créditos:"
                celula_saldo = page.locator("td:has-text('Créditos:') + td")
                await celula_saldo.wait_for(state="visible", timeout=30000)
                saldo_raw = await celula_saldo.inner_text()
            except:
                print("[WORKER] ⚠️ Seletor de vizinho falhou, tentando seletor CSS absoluto...", flush=True)
                # Tentativa 2: Seletor direto na classe que costuma aparecer
                saldo_raw = await page.locator("span.textoCredit").first.inner_text()

            saldo_final = formatar_valor_voip(saldo_raw)
            print(f"✅ Saldo Extraído: {saldo_final}", flush=True)

            # 3. NAVEGAÇÃO PARA RELATÓRIO
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

            return {"saldo_atual": saldo_final, "custo_diario_total": custo_diario, "custo_semanal_acumulado": 0.0}
            
    except Exception as e:
        print(f"❌ Erro Crítico no Scraping: {e}", flush=True)
        return {"erro": str(e)}
    finally:
        if browser: await browser.close()

# ... (Manter funções enviar_para_api e o bloco __main__ do script anterior)



























