# main.py (Scheduler Principal)

import asyncio
import time
import datetime  # Importado para a lógica de horário e dias
from scripts.monitor import run_monitor
from scripts.restart_campaign import restart_campaign
from scripts.daily_mailing_worker import run_daily_import_pipeline

# Lista dos servidores que devem ser monitorados em cada ciclo
SERVERS_TO_MONITOR = ["MG", "SP"]

# Intervalo de Checagem (30 segundos)
CHECK_INTERVAL_SECONDS = 15  # Usando 15s para performance

# --- CONSTANTES DE HORÁRIO DE EXPEDIENTE (PARA MONITORAMENTO) ---
START_HOUR = 9  # 09:00h
START_MINUTE = 30  # 09:30h
END_HOUR = 18  # 18:00h
END_MINUTE = 30  # 18:30h
# --------------------------------------------

# --- CONSTANTES DE EXECUÇÃO DO PIPELINE DE IMPORTAÇÃO (11:00h) ---
DAILY_IMPORT_HOUR = 11
DAILY_IMPORT_MINUTE = 00


# --------------------------------------------


def is_within_operating_hours() -> bool:
    """
    Verifica se o horário e dia atual estão dentro da janela de operação
    (Segunda a Sexta, 09:30h às 18:30h).
    """
    now = datetime.datetime.now()

    # Checagem 1: Dia da Semana (Segunda=0, Domingo=6)
    if now.weekday() >= 5:
        return False

    current_time_minutes = now.hour * 60 + now.minute

    start_time_minutes = START_HOUR * 60 + START_MINUTE
    end_time_minutes = END_HOUR * 60 + END_MINUTE

    if start_time_minutes <= current_time_minutes <= end_time_minutes:
        return True

    return False


async def check_and_act(server: str):
    """
    Executa o monitoramento e acionamento (restart) para um servidor específico.
    """
    # 1. Executa o Monitoramento (Passa o parâmetro 'server' para o worker)
    result = await run_monitor(server=server)
    active_calls = result.get("active_calls", -1)
    status = result.get("status", "ERRO")

    print(f"[{server}] Resultado: {active_calls} active calls. Status: {status}")

    # 2. Lógica Condicional: Acionar Restart se Active Calls == 0
    if active_calls == 0 and status == "OK":
        print(f"🚨 ALERTA [{server}]: Chamadas zeradas. Acionando ROTINA DE RESTART...")

        # 3. Aciona o Restarter (Passa o parâmetro 'server' para o worker)
        success = await restart_campaign(server=server)

        if success:
            print(f"✅ RESTART SUCESSO [{server}]: Campanha reimportada e subida.")
        else:
            print(f"❌ RESTART FALHA [{server}]: Falha na rotina de reimportação.")

    elif active_calls > 0:
        print(f"[{server}] Operação normal. Chamadas ativas: {active_calls}")
    else:
        print(f"[{server}] FALHA CRÍTICA no Monitoramento. Status: {status}")


async def main_scheduler():
    """
    Loop principal que executa o monitoramento e a checagem da rotina diária.
    """
    print("Iniciando Scheduler Principal (Modo Headless Railway)...")

    while True:
        now = datetime.datetime.now()

        # 1. Checagem da Rotina Diária (Horário Fixo: 11:00h)
        if now.hour == DAILY_IMPORT_HOUR and now.minute == DAILY_IMPORT_MINUTE and now.weekday() < 5:
            print("\n--- INICIANDO PIPELINE DE IMPORTAÇÃO DIÁRIA (11:00h) ---")

            # Execução sequencial: Excluir/Importar Mailing Novo em MG e SP
            await run_daily_import_pipeline(server="MG")
            await run_daily_import_pipeline(server="SP")

            # ✅ PAUSA DE SEGURANÇA: CRUCIAL para evitar a execução duplicada no mesmo minuto
            await asyncio.sleep(60)

            # 2. Rotina de Monitoramento Contínuo (09:30h - 18:30h)
        if is_within_operating_hours():
            print(f"\n--- [ATIVO] Ciclo de Monitoramento Iniciado ({now.strftime('%H:%M:%S')}) ---")

            # Executa as checagens de forma sequencial para MG e SP
            await check_and_act(server="MG")
            await check_and_act(server="SP")

        else:
            # A checagem de horário é FALSE, apenas loga o status inativo
            print(
                f"--- [INATIVO] Fora do Horário Comercial ({now.strftime('%H:%M:%S')}). Próxima checagem em {CHECK_INTERVAL_SECONDS} segundos. ---")

        print(f"--- Fim do Ciclo. Aguardando {CHECK_INTERVAL_SECONDS} segundos. ---")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == '__main__':
    try:
        asyncio.run(main_scheduler())
    except KeyboardInterrupt:
        print("Scheduler encerrado.")




