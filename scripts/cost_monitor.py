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
            
            # Aguarda o Dashboard carregar
            saldo_el = "#system-container > div > div:nth-child(2) > div > h3"
            await page.wait_for_selector(saldo_el, timeout=45000)
            saldo_text = await page.text_content(saldo_el)
            print(f"[WORKER-DEBUG] ✅ Saldo extraído: {saldo_text}")

            # --- NAVEGAÇÃO MELHORADA ---
            print("[WORKER-DEBUG] 🖱️ Navegando para Relatórios Agrupados...")
            # Clica no menu principal "Relatórios"
            await page.click('#main-menu > li:nth-child(5) > a') 
            
            # Pequena pausa para garantir que o submenu foi renderizado após o clique
            await page.wait_for_timeout(2000) 
            
            # Clica no item específico usando force=True para evitar bloqueios de sobreposição
            await page.click("#relatorioAgrupadoLinhas", force=True)
            
            print("[WORKER-DEBUG] ⏳ Aguardando tabela de custos (#tblMain)...")
            # Aumentamos o timeout e verificamos visibilidade para evitar o erro anterior
            await page.wait_for_selector("#tblMain", timeout=60000, state="visible")

            print("[WORKER-DEBUG] 📊 Extraindo valores da tabela...")
            
            # Extração resiliente com seletores CSS diretos
            discador_text = "0"
            try:
                discador_text = await page.locator('#tblMain > tbody > tr:nth-child(1) > td:nth-child(7)').text_content(timeout=10000)
                print(f"[WORKER-DEBUG] 📥 Valor Discador: {discador_text}")
            except: 
                print("[WORKER-DEBUG] ⚠️ Linha 1 (Discador) não encontrada ou vazia.")

            ura_text = "0"
            try:
                ura_text = await page.locator('#tblMain > tbody > tr:nth-child(2) > td:nth-child(7)').text_content(timeout=10000)
                print(f"[WORKER-DEBUG] 📥 Valor URA: {ura_text}")
            except: 
                print("[WORKER-DEBUG] ⚠️ Linha 2 (URA) não encontrada ou vazia.")

            dados = {
                "saldo_atual": clean_to_float(saldo_text),
                "custo_diario_total": clean_to_float(discador_text) + clean_to_float(ura_text),
                "custo_semanal_acumulado": 0.0 
            }
            return dados
            
    except Exception as e:
        print(f"[WORKER-ERROR] ❌ Falha no Scraping: {str(e)}")
        return {"erro": str(e)}
    finally:
        if browser: 
            print("[WORKER-DEBUG] 🔒 Fechando navegador...")
            await browser.close()

async def enviar_para_api(dados: Dict[str, Any]):
    print(f"[WORKER-API] 📡 Enviando R$ {dados['custo_diario_total']} para Gateway...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(API_URL_INTERNA, json=dados, timeout=20.0)
            if resp.status_code == 200:
                print("✅ [WORKER-API] Entrega confirmada pela API Gateway.")
            else:
                print(f"❌ [WORKER-API] Erro na API: {resp.status_code}")
        except Exception as e:
            print(f"❌ [WORKER-API] Erro de conexão com a API: {e}")

if __name__ == '__main__':
    print(f"--- [WORKER START] {datetime.now().strftime('%d/%m %H:%M:%S')} ---")
    dados_brutos = asyncio.run(coletar_custos_async())

    if not dados_brutos.get('erro'):
        # Executa o envio para a API Gateway
        asyncio.run(enviar_para_api(dados_brutos)) 
        
        fmt = processar_dados_para_dashboard_formatado(dados_brutos)
        print(f"--- [WORKER FINISH] Saldo: {fmt['saldo_atual']} | Diário: {fmt['custo_diario']} ---")





