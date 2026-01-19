# main.py (Scheduler Principal)

import asyncio
import time
import datetime  # Importado para a lógica de horário e dias
import sys       # Necessário para o comando de restart (exit)
from scripts.monitor import run_monitor
from scripts.restart_campaign import restart_campaign
from scripts.daily_mailing_worker import run_daily_import_pipeline

# Lista dos servidores que devem ser monitorados em cada ciclo
SERVERS_TO_MONITOR = ["MG", "SP"]

# Intervalo de Checagem (30 segundos)
CHECK_INTERVAL_SECONDS = 15  # Usando 15s para performance

# Contador de falhas de login para auto-recuperação
falhas_login_consecutivas = 0

# --- CONSTANTES DE HORÁRIO DE EXPEDIENTE (AJUSTADO PARA UTC/RAILWAY) ---
START_HOUR = 12   # 09:30h + 3h = 12:30h UTC
START_MINUTE = 30
END_HOUR = 21     # 18:30h + 3h = 21:30h UTC
END_MINUTE = 30
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
    Retorna o status para controle de falhas globais.
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
        
    return status


async def main_scheduler():
    """
    Loop principal que executa o monitoramento e a checagem da rotina diária.
    """
    global falhas_login_consecutivas
    print("Iniciando Scheduler Principal (Modo Headless Railway com Auto-Recuperação)...")

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

            # Executa as checagens de forma sequencial para MG e SP e captura os status
            status_mg = await check_and_act(server="MG")
            status_sp = await check_and_act(server="SP")

            # Lógica de Auto-Recuperação: Se ambos falharem o login simultaneamente
            if status_mg == "Login Falhou" and status_sp == "Login Falhou":
                falhas_login_consecutivas += 1
                print(f"⚠️ Instabilidade detectada: {falhas_login_consecutivas}/2 falhas consecutivas de login.")
            else:
                # Reseta o contador se ao menos um servidor estiver operando/logando
                falhas_login_consecutivas = 0

            # Disparo do Restart se atingir o limite de 2 falhas
            if falhas_login_consecutivas >= 2:
                print("🚨 [CRITICAL] 2 falhas de login seguidas detectadas. Forçando RESTART via sys.exit...")
                sys.exit(1) # O Railway detecta o erro e reinicia o container automaticamente

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






