import socket
import struct

# Configurações do servidor
UDP_PORT = 5005
TCP_PORT = 5006


# Função para calcular um checksum simples
def calculate_checksum(data):
    return sum(data) % 256


# Função para escutar e responder a registros e métricas via UDP
def listen_udp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', UDP_PORT))
    print(f"NMS_Server escutando UDP na porta {UDP_PORT}")

    while True:
        data, addr = sock.recvfrom(1024)
        msg_type, sequence_num, agent_id, checksum = struct.unpack('!BHHH', data[:8])

        if msg_type == 1:  # Registro
            print(f"Registro recebido do agente com ID: {agent_id}")
            ack_message = struct.pack('!BHHH', 3, sequence_num, agent_id,
                                      calculate_checksum([3, sequence_num, agent_id]))
            sock.sendto(ack_message, addr)

        elif msg_type == 2:  # Envio de Métricas
            _, _, agent_id, _, task_id, metric_type, metric_value, timestamp = struct.unpack('!BHHHIBIQ', data)
            print(f"Métrica '{metric_type}' do agente {agent_id} - Valor: {metric_value}, Timestamp: {timestamp}")
            ack_message = struct.pack('!BHHH', 3, sequence_num, agent_id,
                                      calculate_checksum([3, sequence_num, agent_id]))
            sock.sendto(ack_message, addr)


# Função para escutar alertas via TCP
def listen_tcp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('', TCP_PORT))
    sock.listen()
    print(f"NMS_Server escutando TCP na porta {TCP_PORT}")

    while True:
        conn, addr = sock.accept()
        data = conn.recv(1024)
        agent_id, alert_type, metric_type, metric_value, threshold, timestamp = struct.unpack('!HBBIIQ', data)
        print(
            f"Alerta recebido do agente {agent_id} - Tipo: {alert_type}, Métrica: {metric_type}, Valor: {metric_value}, Limite: {threshold}, Timestamp: {timestamp}")
        conn.close()


# Executando o servidor
import threading

udp_thread = threading.Thread(target=listen_udp)
tcp_thread = threading.Thread(target=listen_tcp)
udp_thread.start()
tcp_thread.start()
