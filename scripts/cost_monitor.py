# scripts/cost_monitor.py
import os
import asyncio
import redis
from datetime import datetime
from playwright.async_api import async_playwright

# Configurações lidas do ambiente
URL_LOGIN = "http://187.60.56.102:8080/SipPulsePortal/pages/login/login.jsf"
USUARIO = os.getenv("NEXT_ROUTER_USER", "99971111225@sip2.v01p.com.br")
SENHA = os.getenv("NEXT_ROUTER_PASS", "jLEf2LMG8X9t8P7P")

async def coletar():
    print("[WORKER] 🟢 Playwright iniciado...", flush=True)
    async with async_playwright() as p:
        # Argumentos para evitar detecção em nuvem
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0 Safari/537.36")
        page = await context.new_page()

        try:
            print(f"[WORKER] 🌐 Acessando Portal...", flush=True)
            await page.goto(URL_LOGIN, wait_until="load", timeout=60000)
            
            await page.locator('input[id*="login"]').fill(USUARIO)
            await page.locator('input[id*="password"]').fill(SENHA)
            
            print("[WORKER] 🔑 Clicando em Login...", flush=True)
            await page.locator('input[value="Acessar Portal"]').click()
            
            # ESPERA DE OURO: Networkidle garante que o AJAX do JSF terminou
            await page.wait_for_load_state("networkidle", timeout=60000)
            await page.wait_for_timeout(5000) # Pausa extra para renderização de saldo

            # SALDO
            print("[WORKER] 💰 Extraindo Saldo...", flush=True)
            saldo_raw = await page.locator("span.textoCredit").first.inner_text()
            print(f"✅ Saldo Bruto: {saldo_raw}", flush=True)

            # CONSUMO (Caminho validado no seu debug local)
            await page.get_by_text("Chamadas Saintes").click()
            await page.wait_for_load_state("networkidle")
            await page.locator('input[value="Gerar Relatório"]').click()
            
            # XPath Full validado
            xpath_total = "/html/body/table/tbody/tr[4]/td/table/tbody/tr/td[2]/form/table/tbody/tr[2]/td/table/tbody/tr/td/table[2]/tfoot/tr/td[3]"
            await page.wait_for_selector(f"xpath={xpath_total}", state="visible", timeout=60000)
            
            consumo_raw = await page.locator(f"xpath={xpath_total}").inner_text()
            print(f"✅ Consumo Bruto: {consumo_raw}", flush=True)

        except Exception as e:
            print(f"❌ Erro durante o scraping: {e}", flush=True)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(coletar())























