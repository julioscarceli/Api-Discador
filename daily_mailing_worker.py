# scripts/daily_mailing_worker.py

import asyncio
import os
from datetime import datetime
import pandas as pd
import httpx  # Necessário para a API

# --- IMPORTAÇÕES DE FUNÇÕES DO PROJETO ---
from scripts.restart_campaign import finalize_campaign_only
from utils.mailing_api import api_import_mailling_upload
from config.settings import LOCAL_MAILING_BASE_DIR  # Caminho local

# Assumimos que as constantes estão no escopo global ou importadas.
# ----------------------------------------

# --- VARIÁVEIS DE CONTROLE ---
MAILING_FILE_MAP = {"MG": "MAILING_DISCADOR_EMP", "SP": "MAILING_DISCADOR_CARD"}
TEST_IMPORT_ID = "1"
TEST_LOGIN_CRM = "DAILY_IMPORTER"


async def run_daily_import_pipeline(server: str):
    """
    Executa a rotina diária de substituição de mailing: Finalizar (UI) -> Importar (API).
    Chamado pelo main.py no horário de 11:00h.
    """

    server_name = server.upper()
    print(f"\n--- [DAILY IMPORT - {server_name}] INICIANDO PIPELINE DE GESTÃO ---")

    # 1. PREPARAÇÃO DO ARQUIVO (LOCAL)
    TODAY_FILE_SUFFIX = datetime.now().strftime(' - %d-%m') + ".csv"
    base_name = MAILING_FILE_MAP.get(server_name)
    source_file_path = os.path.join(LOCAL_MAILING_BASE_DIR, f"{base_name}{TODAY_FILE_SUFFIX}")

    if not os.path.exists(source_file_path):
        print(f"[{server_name}] ❌ ERRO: Arquivo de origem NÃO ENCONTRADO. Abortando.")
        return False

    # 2. PASSO 1: LIMPEZA/FINALIZAÇÃO DA CAMPANHA ANTIGA (Web Scraping)
    print(f"[{server_name}] 2. Limpeza: Finalizando campanha antiga via UI...")
    clean_success = await finalize_campaign_only(server)

    if not clean_success:
        print(f"[{server_name}] ❌ Alerta: Falha na limpeza. ABORTANDO para evitar conflito.")
        return False

    print(f"[{server_name}] ✅ Limpeza de campanha antiga concluída.")

    # 3. PASSO 2: IMPORTAÇÃO DO NOVO MAILING (API Multipart POST)
    try:
        mailling_name_for_api = base_name + datetime.now().strftime(' - %d-%m')

        upload_result = await api_import_mailling_upload(
            server=server,
            campaign_id=TEST_IMPORT_ID,
            source_csv_path=source_file_path,
            mailling_name=mailling_name_for_api,
            login_crm=TEST_LOGIN_CRM
        )

        if upload_result.get('success'):
            print(f"[{server_name}] ✅ SUCESSO: Upload concluído. ID Lista: {upload_result.get('id_lista', 'N/A')}")

            # 4. PASSO 3: ATIVAÇÃO
            # Aqui entraria a lógica de Web Scraping para ATIVAR a campanha com 70 canais (Se necessário).
            # Por agora, o upload API já cria a campanha, mas a ativação (subir canais) é a próxima etapa.
            print(f"[{server_name}] 4. ATIVAÇÃO PENDENTE: Iniciar discagem com 70 canais.")

        else:
            print(f"[{server_name}] ❌ FALHA NO UPLOAD API: {upload_result.get('token', 'Erro desconhecido')}")
            return False

    except Exception as e:
        print(f"[{server_name}] ❌ ERRO CRÍTICO NO UPLOAD: {e}")
        return False

    print(f"--- [DAILY IMPORT - {server_name}] Pipeline Concluído! ---")
    return True