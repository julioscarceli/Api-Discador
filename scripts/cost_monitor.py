import os
import re
import json
import asyncio
import httpx
from typing import Dict, Any
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

# --- Configurações ---
BASE_URL = os.getenv("NEXT_ROUTER_URL")
USUARIO = os.getenv("NEXT_ROUTER_USER")
SENHA = os.getenv("NEXT_ROUTER_PASS")
# URL da sua API Gateway no Railway
API_URL_INTERNA = "https://api-discador-production.up.railway.app/api/atualizar-custos"

def clean_to_float(value):
    if value == "—" or value is None: return 0.0
    try:
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

            print(f"[WORKER-DEBUG] 🌐 Acessando roteador em: {BASE_URL}")
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
            
            await page.fill("#username", USUARIO)
            await page.fill("#password", SENHA)
            await page.click('button:has-text("Conectar")')
            
            # 1. Extração do Saldo (Sempre visível após login)
            saldo_el = "#system-container > div > div:nth-child(2) > div > h3"
            await page.wait_for_selector(saldo_el, timeout=45000)
            saldo_text = await page.text_content(saldo_el)
            print(f"[WORKER-DEBUG] ✅ Saldo extraído: {saldo_text}")

            # 2. Navegação para Relatórios
            print("[WORKER-DEBUG] 🖱️ Navegando para Relatórios Agrupados...")
            await page.click('#main-menu > li:nth-child(5) > a') 
            await page.wait_for_timeout(2000) 
            await page.click("#relatorioAgrupadoLinhas", force=True)
            
            # --- LÓGICA DE VERIFICAÇÃO DE CONSUMO ---
            print("[WORKER-DEBUG] ⏳ Verificando se há consumo registrado hoje...")
            custo_diario = 0.0
            try:
                # Tenta localizar a tabela por apenas 15 segundos
                await page.wait_for_selector("#tblMain", timeout=15000, state="visible")
                print("[WORKER-DEBUG] 📊 Tabela encontrada. Extraindo valores...")
                
                # Extração das linhas de Discador e URA
                discador_text = "0"
                try:
                    discador_text = await page.locator('#tblMain > tbody > tr:nth-child(1) > td:nth-child(7)').text_content(timeout=5000)
                except: pass

                ura_text = "0"
                try:
                    ura_text = await page.locator('#tblMain > tbody > tr:nth-child(2) > td:nth-child(7)').text_content(timeout=5000)
                except: pass
                
                custo_diario = clean_to_float(discador_text) + clean_to_float(ura_text)
                
            except Exception:
                # Caso a tabela não apareça, o custo é zero (o roteador não gera a tabela sem dados)
                print("[WORKER-DEBUG] ℹ️ Tabela não localizada. Assumindo custo zero para o dia.")
                custo_diario = 0.0

            dados = {
                "saldo_atual": clean_to_float(saldo_text),
                "custo_diario_total": custo_diario,
                "custo_semanal_acumulado": 0.0 
            }
            return dados
            
    except Exception as e:
        print(f"[WORKER-ERROR] ❌ Erro Crítico durante a coleta: {str(e)}")
        return {"erro": str(e)}
    finally:
        if browser: 
            print("[WORKER-DEBUG] 🔒 Fechando navegador...")
            await browser.close()

async def enviar_para_api(dados: Dict[str, Any]):
    print(f"[WORKER-API] 📡 Enviando dados para Gateway (Diário: R$ {dados['custo_diario_total']})...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(API_URL_INTERNA, json=dados, timeout=20.0)
            if resp.status_code == 200:
                print("✅ [WORKER-API] Entrega confirmada pela API Gateway.")
            else:
                print(f"❌ [WORKER-API] Erro na API: {resp.status_code}")
        except Exception as e:
            print(f"❌ [WORKER-API] Falha de conexão: {e}")

if __name__ == '__main__':
    print(f"--- [WORKER START] {datetime.now().strftime('%d/%m %H:%M:%S')} ---")
    dados_brutos = asyncio.run(coletar_custos_async())

    if not dados_brutos.get('erro'):
        # Envia os resultados para a API
        asyncio.run(enviar_para_api(dados_brutos)) 
        
        fmt = processar_dados_para_dashboard_formatado(dados_brutos)
        print(f"--- [WORKER FINISH] Saldo: {fmt['saldo_atual']} | Diário: {fmt['custo_diario']} ---")






