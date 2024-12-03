import socket
import struct
import collections
import json

# Configurações do servidor
UDP_PORT = 5005
TCP_PORT = 5006

# Histórico de sequências processadas (máximo de 100 entradas por agente para economizar memória)
sequence_history = collections.defaultdict(lambda: collections.deque(maxlen=100))

# Função para calcular um checksum simples
def calculate_checksum(data):
    return sum(data) % 256

# Função para salvar métricas recebidas
def save_metric(agent_id, task_id, metric_type, metric_value, timestamp):
    data = {
        "agent_id": agent_id,
        "task_id": task_id,
        "metric_type": metric_type,
        "metric_value": metric_value,
        "timestamp": timestamp
    }

    # Ler o arquivo existente ou criar uma nova lista
    try:
        with open("metrics.json", "r") as file:
            metrics = json.load(file)  # Carregar dados existentes
    except (FileNotFoundError, json.JSONDecodeError):
        metrics = []  # Iniciar nova lista se o arquivo não existir ou estiver vazio

    # Adicionar a nova métrica
    metrics.append(data)

    # Escrever a lista atualizada no arquivo
    with open("metrics.json", "w") as file:
        json.dump(metrics, file, indent=4)  # Salvar no formato JSON

# Função para salvar alertas recebidos
def save_alert(agent_id, metric_type, metric_value, threshold, timestamp):
    # Estrutura do alerta
    alert_data = {
        "agent_id": agent_id,
        "metric_type": metric_type,
        "metric_value": metric_value,
        "threshold": threshold,
        "timestamp": timestamp
    }

    # Ler o arquivo existente ou criar uma nova lista
    try:
        with open("alerts.json", "r") as file:
            alerts = json.load(file)  # Carregar dados existentes
    except (FileNotFoundError, json.JSONDecodeError):
        alerts = []  # Iniciar nova lista se o arquivo não existir ou estiver vazio

    # Adicionar o novo alerta
    alerts.append(alert_data)

    # Escrever a lista atualizada no arquivo
    with open("alerts.json", "w") as file:
        json.dump(alerts, file, indent=4)  # Salvar no formato JSON
    print(f"Alerta salvo: {alert_data}")

# Função para escutar e responder a registros e métricas via UDP
def listen_udp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', UDP_PORT))
    print(f"NMS_Server escutando UDP na porta {UDP_PORT}")

    while True:
        data, addr = sock.recvfrom(1024)
        print(f"Recebido {len(data)} bytes: {data}")

        # Verificação do tamanho mínimo antes de identificar o tipo
        if len(data) < 7:  # 7 bytes é o tamanho mínimo para qualquer mensagem válida
            print(f"Pacote inválido recebido (tamanho {len(data)}): {data}")
            continue

        # Identificar o tipo da mensagem
        msg_type = data[0]  # Primeiro byte indica o tipo da mensagem

        if msg_type == 1:  # Registro
            # Garantir que o pacote de registro tem o tamanho correto (7 bytes)
            if len(data) != 7:
                print(f"Pacote de registro inválido (tamanho {len(data)}): {data}")
                continue

            # Desempacotar o pacote de registro
            try:
                _, sequence_num, agent_id, checksum = struct.unpack('!BHHH', data)
                print(f"Registro recebido do agente com ID: {agent_id}")
                ack_message = struct.pack('!BHHH', 3, sequence_num, agent_id,
                                          calculate_checksum([3, sequence_num, agent_id]))
                sock.sendto(ack_message, addr)
            except struct.error as e:
                print(f"Erro ao desempacotar registro: {e}, pacote: {data}")
                continue

        elif msg_type == 2:  # Métrica
            if len(data) != 26:  # Verifica o tamanho necessário para o formato completo
                print(f"Pacote de métrica incompleto recebido (tamanho {len(data)}): {data}")
                continue

            # Desempacotar o pacote de métrica
            try:
                _, sequence_num, agent_id, checksum, task_id, metric_type, metric_value, timestamp, _ = struct.unpack(
                '!BHHHIBIQH', data)

                if sequence_num in sequence_history[agent_id]:
                    print(f"Pacote duplicado ignorado do agente {agent_id}, sequência {sequence_num}")
                    continue

                # Adicionar sequência ao histórico
                sequence_history[agent_id].append(sequence_num)

                # Processar métrica
                print(f"Métrica recebida - Agente: {agent_id}, Tipo: {metric_type}, Valor: {metric_value}, Timestamp: {timestamp}")

                # Salvar a métrica no arquivo
                save_metric(agent_id, task_id, metric_type, metric_value, timestamp)

                # Lógica para determinar sobrecarga
                too_much_traffic = len(sequence_history[agent_id]) > 5
                
                # Gerar o ACK com sinal de controle de fluxo
                flow_control_flag = 1 if too_much_traffic else 0
                ack_message = struct.pack('!BHHHB', 3, sequence_num, agent_id,
                          calculate_checksum([3, sequence_num, agent_id]), flow_control_flag)
                sock.sendto(ack_message, addr)

                if flow_control_flag == 1:
                    print(f"Controle de fluxo ativado para o agente {agent_id}: reduzir frequência de envio.")
                    
            except struct.error as e:
                print(f"Erro ao desempacotar métrica: {e}, pacote: {data}")
                continue
        else:
            print(f"Tipo de mensagem desconhecido: {msg_type}, pacote: {data}")

# Escutar alertas via TCP
def listen_tcp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('', TCP_PORT))
    sock.listen()
    print(f"NMS_Server escutando TCP na porta {TCP_PORT}")

    while True:
        conn, addr = sock.accept()
        print(f"Conexão TCP estabelecida com {addr}")
        data = conn.recv(1024)

        if len(data) != 20:  # Verifica o tamanho esperado do pacote
            print(f"Pacote inválido recebido (tamanho {len(data)}): {data}")
        else:
            try:
                # Desempacotar os dados do alerta
                agent_id, alert_type, metric_type, metric_value, threshold, timestamp = struct.unpack('!HBBIIQ', data)
                print(f"Alerta recebido do Agente {agent_id} - Tipo: {metric_type}, "
                      f"Valor: {metric_value}, Limite: {threshold}, Timestamp: {timestamp}")

                # Salvar o alerta no arquivo
                save_alert(agent_id, metric_type, metric_value, threshold, timestamp)

            except struct.error as e:
                print(f"Erro ao desempacotar alerta: {e}, pacote: {data}")
        
        conn.close()

# Executando o servidor
import threading

udp_thread = threading.Thread(target=listen_udp)
tcp_thread = threading.Thread(target=listen_tcp)
udp_thread.start()
tcp_thread.start()
