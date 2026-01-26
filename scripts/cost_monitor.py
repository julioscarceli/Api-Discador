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
BASE_URL = os.getenv("NEXT_ROUTER_URL")
USUARIO = os.getenv("NEXT_ROUTER_USER")
SENHA = os.getenv("NEXT_ROUTER_PASS")
API_URL_INTERNA = "https://api-discador-production.up.railway.app/api/atualizar-custos"

# Configuração do Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://default:BMetYritSRFXIbozyBtCQpJpQKOxnnZE@redis.railway.internal:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

def clean_to_float(value):
    if value == "—" or value is None: return 0.0
    try:
        # Remove R$, espaços e ajusta separadores decimais
        value = re.sub(r'[^\d,.]', '', str(value))
        return float(value.replace('.', '').replace(',', '.'))
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
        print("\n[WORKER-DEBUG] 🟢 Iniciando Playwright...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless, 
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            context = await browser.new_context(ignore_https_errors=True)
            page = await context.new_page()

            # Bloqueio de recursos inúteis para economizar banda/tempo
            await page.route("**/*.{png,jpg,jpeg,css}", lambda route: route.abort())

            print(f"[WORKER-DEBUG] 🌐 Acessando roteador em: {BASE_URL}")
            await page.goto(BASE_URL, wait_until="commit", timeout=60000)
            
            # Login Otimizado
            await page.locator("#username").fill(USUARIO)
            await page.locator("#password").fill(SENHA)
            await page.click('button:has-text("Conectar")')
            
            # 1. Extração do Saldo
            saldo_el = "#system-container > div > div:nth-child(2) > div > h3"
            await page.wait_for_selector(saldo_el, timeout=45000)
            saldo_text = await page.text_content(saldo_el)
            print(f"[WORKER-DEBUG] ✅ Saldo extraído: {saldo_text}")

            # 2. Navegação para Relatórios
            print("[WORKER-DEBUG] 🖱️ Navegando para Relatórios Agrupados...")
            await page.click('#main-menu > li:nth-child(5) > a') 
            await asyncio.sleep(2) 
            await page.click("#relatorioAgrupadoLinhas", force=True)
            
            # 3. Extração de Consumo Hoje
            custo_diario = 0.0
            try:
                await page.wait_for_selector("#tblMain", timeout=15000, state="visible")
                discador_text = await page.locator('#tblMain > tbody > tr:nth-child(1) > td:nth-child(7)').text_content(timeout=5000)
                ura_text = await page.locator('#tblMain > tbody > tr:nth-child(2) > td:nth-child(7)').text_content(timeout=5000)
                custo_diario = clean_to_float(discador_text) + clean_to_float(ura_text)
            except:
                print("[WORKER-DEBUG] ℹ️ Tabela de hoje vazia ou não carregada.")

            # --- LÓGICA REDIS: ACUMULADO SEMANAL (Segunda a Hoje) ---
            hoje = datetime.now()
            hoje_str = hoje.strftime('%Y-%m-%d')
            
            # Salva o custo do dia atual (expira em 8 dias)
            r.set(f"custo_hist_{hoje_str}", str(custo_diario), ex=691200)

            # Calcula o range de Segunda-feira (0) até Hoje
            dias_desde_segunda = hoje.weekday() 
            total_semanal = 0.0
            
            # Itera apenas os dias da semana corrente
            for i in range(dias_desde_segunda + 1):
                data_busca = (hoje - timedelta(days=i)).strftime('%Y-%m-%d')
                val = r.get(f"custo_hist_{data_busca}")
                if val:
                    total_semanal += float(val)

            dados = {
                "saldo_atual": clean_to_float(saldo_text),
                "custo_diario_total": custo_diario,
                "custo_semanal_acumulado": total_semanal 
            }
            return dados
            
    except Exception as e:
        print(f"[WORKER-ERROR] ❌ Erro Crítico: {str(e)}")
        return {"erro": str(e)}
    finally:
        if browser: 
            await browser.close()

async def enviar_para_api(dados: Dict[str, Any]):
    print(f"[WORKER-API] 📡 Enviando dados para Gateway...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(API_URL_INTERNA, json=dados, timeout=20.0)
            if resp.status_code == 200:
                print("✅ [WORKER-API] Entrega confirmada.")
            else:
                print(f"❌ [WORKER-API] Erro: {resp.status_code}")
        except Exception as e:
            print(f"❌ [WORKER-API] Falha de conexão: {e}")

if __name__ == '__main__':
    print(f"--- [WORKER START] {datetime.now().strftime('%d/%m %H:%M:%S')} ---")
    dados_brutos = asyncio.run(coletar_custos_async())
    if not dados_brutos.get('erro'):
        asyncio.run(enviar_para_api(dados_brutos)) 
        fmt = processar_dados_para_dashboard_formatado(dados_brutos)
        print(f"--- [WORKER FINISH] Saldo: {fmt['saldo_atual']} | Diário: {fmt['custo_diario']} | Semanal: {fmt['custo_semanal']} ---")









