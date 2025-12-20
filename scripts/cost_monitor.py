# scripts/cost_monitor.py (VERSÃO COM ENVIO HTTP PARA A API)

import os
import re
import json
import asyncio
import sys
import httpx  # 🚨 NECESSÁRIO: pip install httpx
from typing import Dict, Any
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

load_dotenv()

# --- Configurações ---
BASE_URL = os.getenv("NEXT_ROUTER_URL")
USUARIO = os.getenv("NEXT_ROUTER_USER")
SENHA = os.getenv("NEXT_ROUTER_PASS")
API_URL_INTERNA = "https://api-discador-production.up.railway.app/api/atualizar-custos"

def clean_to_float(value):
    if value == "—": return None
    try:
        value = re.sub(r'[^\d,.]', '', value or "")
        return float(value.replace('.', '').replace(',', '.'))
    except: return None

def processar_dados_para_dashboard_formatado(d: Dict[str, Any]) -> Dict[str, Any]:
    saldo = f"R$ {d.get('saldo_atual', 0):.2f}".replace('.', ',') if d.get('saldo_atual') is not None else "N/A"
    custo = f"R$ {d.get('custo_diario_total', 0):.2f}".replace('.', ',') if d.get('custo_diario_total') is not None else "N/A"
    custo_semanal = f"R$ {d.get('custo_semanal_acumulado', 0):.2f}".replace('.', ',') if d.get('custo_semanal_acumulado') is not None else "N/A"

    return {
        "saldo_atual": saldo,
        "custo_diario": custo,
        "custo_semanal": custo_semanal,
        "data_coleta": datetime.now().isoformat()
    }

async def coletar_custos_async(headless: bool = True) -> Dict[str, Any]:
    browser = None
    try:
        print("\n[DEBUG] 🟢 Iniciando contexto do Playwright...")
        async with async_playwright() as p:
            print("[DEBUG] 🚀 Lançando navegador Chromium...")
            # Adicionados argumentos extras para evitar travamentos no Railway
            browser = await p.chromium.launch(
                headless=headless, 
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage", 
                    "--disable-gpu"
                ]
            )
            
            print("[DEBUG] 📄 Abrindo nova página...")
            context = await browser.new_context(ignore_https_errors=True)
            page = await context.new_page()

            print(f"[DEBUG] 🌐 Acessando URL: {BASE_URL}")
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
            
            print("[DEBUG] 🔑 Preenchendo credenciais de login...")
            await page.fill("#username", USUARIO)
            await page.fill("#password", SENHA)
            await page.click('button:has-text("Conectar")')
            
            print("[DEBUG] ⏳ Aguardando carregamento do Dashboard (Saldo)...")
            saldo_el = "#system-container > div > div:nth-child(2) > div > h3"
            await page.wait_for_selector(saldo_el, timeout=45000)
            saldo_text = await page.text_content(saldo_el)
            print(f"[DEBUG] ✅ Saldo localizado: {saldo_text}")

            print("[DEBUG] 🖱️ Navegando para Relatórios Agrupados...")
            await page.click('//*[@id="main-menu"]/li[5]/a') # Dropdown Relatórios
            await page.click("#relatorioAgrupadoLinhas")
            
            print("[DEBUG] ⏳ Aguardando tabela de custos (#tblMain)...")
            await page.wait_for_selector("#tblMain", timeout=45000)

            print("[DEBUG] 📊 Extraindo valores da tabela...")
            discador = await page.text_content('//*[@id="tblMain"]/tbody/tr[1]/td[7]')
            ura = await page.text_content('//*[@id="tblMain"]/tbody/tr[2]/td[7]')
            
            print(f"[DEBUG] 📥 Valores brutos: Discador={discador}, URA={ura}")

            dados = {
                "saldo_atual": clean_to_float(saldo_text),
                "custo_diario_total": (clean_to_float(discador) or 0) + (clean_to_float(ura) or 0),
                "custo_semanal_acumulado": 0.0 # Calculado na API via lógica de RAM
            }
            
            print("[DEBUG] ✨ Coleta concluída com sucesso!")
            return dados

    except Exception as e:
        print(f"[DEBUG] ❌ ERRO DURANTE O SCRAPING: {str(e)}")
        return {"erro": str(e)}
        
    finally:
        if browser:
            print("[DEBUG] 🔒 Fechando navegador...")
            await browser.close()

async def enviar_para_api(dados: Dict[str, Any]):
    # async with: Abre uma conexão temporária com a internet (cliente) e garante 
    # que ela seja fechada após o uso para não gastar memória.
    """Envia os dados coletados para a API Gateway via HTTP."""
    async with httpx.AsyncClient() as client:
        try:
            # await: Diz ao script "espere a resposta da internet sem travar o resto do sistema".
            # client.post: O comando de "empurrar" dados.
            # API_URL_INTERNA: O endereço de destino (sua API no Railway).
            # json=dados: Transforma o dicionário Python em um formato que a web entende (JSON).
            # timeout=20.0: Se a API não responder em 20 segundos, desista (evita que o script fique travado para sempre).
            await client.post(API_URL_INTERNA, json=dados, timeout=20.0)
            print("✅ Dados enviados com sucesso para a API Gateway!")
        except Exception as e:
            # Se a internet cair ou a URL estiver errada, captura o erro e avisa o que houve.
            print(f"❌ Erro ao enviar para a API: {e}")

if __name__ == '__main__':
    print("Iniciando Worker de Scraping...")
    dados_brutos = asyncio.run(coletar_custos_async())

    if not dados_brutos.get('erro'):
        # 🚨 Lógica de acumulação semanal simplificada (pode ser expandida depois)
        dados_brutos['custo_semanal_acumulado'] = dados_brutos['custo_diario_total'] 
        
        # Envia para a API em vez de salvar em arquivo
        asyncio.run(enviar_para_api(dados_brutos))
        
        fmt = processar_dados_para_dashboard_formatado(dados_brutos)
        print(f"| SALDO: {fmt['saldo_atual']} | DIA: {fmt['custo_diario']} |")


