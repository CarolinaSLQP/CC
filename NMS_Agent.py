import sys
import json
import socket
import struct
import time
import threading
from ping3 import ping


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


def send_metric(task, agent_id, server_ip, udp_port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sequence_num = 1

    # Mapear task_id e metric_type
    task_id = int(task["task_id"].split('-')[1])  # Extrai número do ID
    metric_types = {
        "latency": 1,
        "cpu_usage": 2,
        "bandwidth": 3
    }
    metric_type = metric_types[task["metric_type"]]

    frequency = task["frequency"]

    while True:
        # Calcular a latência para o endereço do servidor
        try:
            latency = ping(server_ip)  # Retorna o tempo em segundos
            if latency is None:
                metric_value = -1  # Indica que o destino está inacessível
            else:
                metric_value = int(latency * 1000)  # Converte para milissegundos
        except Exception as e:
            print(f"Erro ao calcular latência: {e}")
            metric_value = -1  # Define como -1 em caso de erro

        timestamp = int(time.time())
        checksum = sum([2, sequence_num, agent_id, metric_value]) % 256

        # Empacotamento da mensagem corrigido
        message = struct.pack('!BHHHIBIQH', 2, sequence_num, agent_id, checksum, task_id, metric_type,
                          metric_value, timestamp, 0)

        # Enviar e processar ACK
        sock.sendto(message, (server_ip, udp_port))
        data, _ = sock.recvfrom(1024)
        if len(data) == 8:  # Verifica se o buffer tem o tamanho correto
            ack_msg_type, ack_sequence_num, ack_agent_id, ack_checksum, flow_control_flag = struct.unpack('!BHHHB', data)
            if ack_msg_type == 3 and ack_sequence_num == sequence_num:
                print(f"Métrica '{task['metric_type']}' enviada e confirmada.")

                # Ajustar a frequência com base no controle de fluxo
                if flow_control_flag == 1:
                    print("Controle de fluxo recebido: reduzindo frequência de envio.")
                    frequency += 5  # Aumenta o intervalo de envio
        else:
            print(f"ACK inválido recebido: {data}")


        if ack_msg_type == 3 and ack_sequence_num == sequence_num:
            print(f"Métrica '{task['metric_type']}' enviada e confirmada.")

            # Ajustar a frequência com base no controle de fluxo
            if flow_control_flag == 1:
                print("Controle de fluxo recebido: reduzindo frequência de envio.")
                frequency += 5  # Aumenta o intervalo de envio (por exemplo, +5 segundos)


        
        # Verificar limite crítico e enviar alerta
        if metric_value > task["threshold"]:  # Usa o limite do JSON
            send_alert(agent_id, metric_type, metric_value, task["threshold"], server_ip, task["tcp_port"])

        sequence_num += 1
        time.sleep(frequency)

# Enviar alerta com base nas tarefas
def send_alert(agent_id, metric_type, metric_value, threshold, server_ip, tcp_port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print(f"Preparando alerta: Agente {agent_id}, Métrica {metric_type}, Valor {metric_value}, Limite {threshold}")
        sock.connect((server_ip, tcp_port))
        alert_message = struct.pack('!HBBIIQ', agent_id, 1, metric_type, metric_value, threshold, int(time.time()))
        sock.sendall(alert_message)
        print(f"Alerta enviado: Agente {agent_id}, Métrica {metric_type}, Valor {metric_value}, Limite {threshold}")
    except Exception as e:
        print(f"Erro ao enviar alerta: {e}")
    finally:
        sock.close()




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
