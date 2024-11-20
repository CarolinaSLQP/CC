import sys
import json
import socket
import struct
import time
import threading


# Função para carregar as configurações de um agente específico
def load_agent_config(config_file, agent_id):
    with open(config_file, "r") as file:
        config = json.load(file)

    for agent in config["agents"]:
        if agent["agent_id"] == agent_id:
            return {
                "agent_id": agent["agent_id"],
                "tasks": agent["tasks"],
                "server_ip": config["server_ip"],
                "udp_port": config["udp_port"],
                "tcp_port": config["tcp_port"]
            }
    raise ValueError(f"Agente com ID {agent_id} não encontrado no arquivo de configuração.")


# Modificar a função register_agent para receber argumentos
def register_agent(agent_id, server_ip, udp_port):
    print(f"Tentando registrar o agente com ID: {agent_id} no servidor...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Dados para registro
    msg_type = 1  # Registro
    sequence_num = 0
    checksum = sum([msg_type, sequence_num, agent_id]) % 256

    # Empacotamento da mensagem
    message = struct.pack('!BHHH', msg_type, sequence_num, agent_id, checksum)

    # Envio e espera de confirmação
    sock.sendto(message, (server_ip, udp_port))
    try:
        data, _ = sock.recvfrom(1024)
        ack_msg_type, ack_sequence_num, ack_agent_id, ack_checksum = struct.unpack('!BHHH', data)
        if ack_msg_type == 3 and ack_agent_id == agent_id:
            print(f"Registro confirmado para o agente com ID: {agent_id}")
            return True
    except Exception as e:
        print(f"Erro ao registrar o agente: {e}")
    print(f"Registro falhou para o agente com ID: {agent_id}")
    return False


# Enviar métricas com base nas tarefas
def send_metric(task, agent_id, server_ip, udp_port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sequence_num = 1
    metric_type = task["metric_type"]
    frequency = task["frequency"]

    while True:
        # Simulação de coleta de métricas
        metric_value = 100  # Exemplo de valor da métrica
        timestamp = int(time.time())
        checksum = sum([2, sequence_num, agent_id, metric_value]) % 256

        # Empacotamento da mensagem
        message = struct.pack('!BHHHIBIQH', 2, sequence_num, agent_id, checksum, task["task_id"], metric_type,
                              metric_value, timestamp)

        # Envio e confirmação
        sock.sendto(message, (server_ip, udp_port))
        data, _ = sock.recvfrom(1024)
        ack_msg_type, ack_sequence_num, ack_agent_id, ack_checksum = struct.unpack('!BHHH', data)

        if ack_msg_type == 3 and ack_sequence_num == sequence_num:
            print(f"Métrica '{metric_type}' enviada e confirmada.")
        sequence_num += 1
        time.sleep(frequency)


# Inicialização principal
if __name__ == "__main__":
    # Obter o ID do agente como argumento
    if len(sys.argv) != 3:
        print("Uso: python3 NMS_Agent.py <config_file> <agent_id>")
        sys.exit(1)

    config_file = sys.argv[1]
    agent_id = int(sys.argv[2])

    # Carregar as configurações do agente
    try:
        config = load_agent_config(config_file, agent_id)
    except ValueError as e:
        print(e)
        sys.exit(1)

    if register_agent(config["agent_id"], config["server_ip"], config["udp_port"]):
        # Iniciar envio de métricas para cada tarefa
        threads = []
        for task in config["tasks"]:
            thread = threading.Thread(target=send_metric,
                                      args=(task, config["agent_id"], config["server_ip"], config["udp_port"]))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()