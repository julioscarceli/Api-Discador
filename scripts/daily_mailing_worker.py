# scripts/daily_mailing_worker.py (VERSÃO ORIGINAL RESTAURADA)
import asyncio
import os
from datetime import datetime
import pandas as pd
import httpx
from scripts.restart_campaign import finalize_campaign_only
from utils.mailing_api import api_import_mailling_upload
from config.settings import LOCAL_MAILING_BASE_DIR

MAILING_FILE_MAP = {"MG": "MAILING_DISCADOR_EMP", "SP": "MAILING_DISCADOR_CARD"}
TEST_IMPORT_ID = "1"
TEST_LOGIN_CRM = "DAILY_IMPORTER"

async def run_daily_import_pipeline(server: str):
    server_name = server.upper()
    TODAY_FILE_SUFFIX = datetime.now().strftime(' - %d-%m') + ".csv"
    base_name = MAILING_FILE_MAP.get(server_name)
    source_file_path = os.path.join(LOCAL_MAILING_BASE_DIR, f"{base_name}{TODAY_FILE_SUFFIX}")

    if not os.path.exists(source_file_path):
        return False

    clean_success = await finalize_campaign_only(server)
    if not clean_success:
        return False

    try:
        upload_result = await api_import_mailling_upload(
            server=server,
            campaign_id=TEST_IMPORT_ID,
            source_csv_path=source_file_path,
            mailling_name=base_name,
            login_crm=TEST_LOGIN_CRM
        )
        return upload_result.get('success')
    except Exception:
        return False


