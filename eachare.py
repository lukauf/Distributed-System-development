import socket
import threading
import sys
import os

class Peer:
    def __init__(self, address, port, neighbors_file, shared_dir):
        self.address = address
        self.port = int(port) #Conversão das portas para inteiro pois as funções da biblioteca socket exigem que ela seja um número
        self.clock = 0  # Relógio lógico
        self.neighbors = self.load_neighbors(neighbors_file)
        self.shared_dir = shared_dir
        self.validate_shared_directory()
        self.status = "ONLINE" #Status do peer carregado
        self.lock = threading.Lock()

    def validate_shared_directory(self):
        """Verifica se o diretório de compartilhamento é válido."""
        if not os.path.isdir(self.shared_dir):
            print(f"Erro: O diretório {self.shared_dir} não é válido ou não pode ser lido.")
            sys.exit(1)
        
    def load_neighbors(self, filename):
        """Carrega a lista inicial de peers vizinhos do arquivo."""
        neighbors = {}
        try:
            with open(filename, 'r') as file:
                for line in file:
                    peer = line.strip()
                    neighbors[peer] = "OFFLINE"
                    print(f"Adicionando novo peer {peer} status OFFLINE")
        except FileNotFoundError:
            print(f"Arquivo de vizinhos {filename} não encontrado.")
            sys.exit(1)
        return neighbors

    def start_server(self):
        #Inicia o servidor TCP para receber conexões de outros peers
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((self.address, self.port))
        server.listen(5)
        
        while True:
            client_socket, client_address = server.accept()
            threading.Thread(target=self.handle_client, args=(client_socket,)).start()

    #Funcao para enviar a lista de peers caso a mensagem recebida seja do tipo GET_PEERS
    def send_peer_list(self, dest_address):
        dest_ip, dest_port = dest_address.split(":")
        #Filtra a lista pra excluir o remetente
        with self.lock:
            peers_info = [
                f"{peer}:{status}:0"
                for peer, status in self.neighbors.items()
                if peer != dest_address  # Nao inclui o peer que pediu a lista
            ]
        
        self.send_message(dest_ip, dest_port, "PEER_LIST", str(len(peers_info)), *peers_info)

    #Funcao para adicionar a lista de vizinhos para o peer que chamou GET_PEERS
    def process_peer_list(self, message):
        parts = message.split()
        if len(parts) < 4 or parts[2] != "PEER_LIST":
            print("Formato inválido para PEER_LIST.")
            return
        
        origem = parts[0]
        num_peers = int(parts[3])
        peers_info = parts[4:4 + num_peers]  # Lista de peers

        print(f"Recebido PEER_LIST de {origem}, contendo {num_peers} peers.")

        with self.lock:
            copia_dict = list(self.neighbors.keys()) #Faz copia das chaves do dicionario para servir de base pra iteracao

        atualizacoes = {} #Criando novo dicionario para nao haver erros de RunTime durante a iteracao (tamanho alterado)
        
        for peer_info in peers_info:
            peer_address, status, _ = peer_info.rsplit(":", 2)  #Divide no formato correto, pegando de dois em dois (endereco e porta)
            if peer_address not in copia_dict:
                print(f"Adicionando novo peer {peer_address} status {status}")
            
            #Aqui o status pode ser atualizado para OFFLINE (mesmo estando online para aquele peer anteriormente), segundo interpretacao do PEER_LIST recebido
            else:
                print(f"Atualizando peer conhecido {peer_address} status {status}")
            atualizacoes[peer_address] = status  # Atualiza ou adiciona o peer

        #Trava para evitar concorrência, pois ao enviar um GET_PEERS, há acesso ao dicionário enquanto se atualiza a lista de peers
        with self.lock:
            self.neighbors = {**self.neighbors, **atualizacoes} #Entao o dicionario original é atualizado 


    #Trata as mensagens recebidas de outros peers
    def handle_client(self, conn):
        try:
            message = conn.recv(1024).decode().strip()
            if not message:
                return
            
            #Divide cada parte da mensagem e verifica se ha 3 argumentos
            parts = message.split()
            if len(parts) < 3:
                print("Mensagem inválida!")
                return

            #Endereco de origem, clock do remetente, tipo de mensagem
            origem, rem_clock, message_type = parts[:3]

            self.clock += 1  # Atualiza o relogio ao receber uma mensagem
            print(f"=> Atualizando relogio para {self.clock}")

            if message_type == "HELLO":
                print(f"Mensagem recebida: \"{message}\"")

                if origem not in self.neighbors:
                    print(f"Adicionando novo peer {origem} status ONLINE")
                else:
                    print(f"Atualizando peer {origem} status ONLINE")

                # Atualiza ou adiciona peer remetente como ONLINE
                with self.lock:
                    self.neighbors[origem] = "ONLINE"

            #Peer envia a lista de vizinhos
            elif message_type == "GET_PEERS":
                self.send_peer_list(origem)

            #Peer recebe a resposta do peer que lhe envioyu GET_PEERS
            elif message_type == "PEER_LIST":
                print(f"Resposta recebida: \"{message}\"")
                self.process_peer_list(message)  # Atualiza a lista de peers

            elif message_type == "BYE":
                print(f"Mensagem recebida: \"{message}\"")
                #Atualiza o status do peer que enviou a mensagem para OFFLINE
                with self.lock:
                    self.neighbors[origem] = "OFFLINE"
                
                print(f"Atualizando peer {origem} status OFFLINE")

            print("> ")

        except Exception as e:
            print(f"Erro ao processar mensagem: {e}")
        finally:
            conn.close()

    
    #Envia uma mensagem para um peer especifico.
    def send_message(self, dest_ip, dest_port, message_type, *args):
        self.clock += 1  # Incrementa o clock logico
        print(f"Atualizando relogio para {self.clock}")
        #Cria a mensagem para o formato especificado
        message = f"{self.address}:{self.port} {self.clock} {message_type}" + \
              (f" {' '.join(args)}" if args else "")
        print(f"Encaminhando mensagem \"{message}\" para {dest_ip}:{dest_port}")
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3)  # Evita travar o código caso o envio dê errado
                s.connect((dest_ip, int(dest_port)))
                s.sendall(message.encode())

            #Se enviou com sucesso, atualiza status do vizinho para ONLINE
            #Se for uma mensagem BYE, não mostramos a atualização de status para seguir o exemplo que consta no pdf do EP
            if not (message_type == "BYE"):
                #Protegendo atualizacao do dicionario
                with self.lock:
                    self.neighbors[f"{dest_ip}:{dest_port}"] = "ONLINE"
                print(f"Atualizando peer {dest_ip}:{dest_port} status ONLINE")

        # Se falhou, marca como OFFLINE
        except (socket.error, socket.timeout):
            with self.lock:
                self.neighbors[f"{dest_ip}:{dest_port}"] = "OFFLINE"
            print(f"Atualizando peer {dest_ip}:{dest_port} status OFFLINE")



if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Uso: python eachare.py <endereco>:<porta> <vizinhos.txt> <diretorio_compartilhado>")
        sys.exit(1)
    
    address, port = sys.argv[1].split(":")
    neighbors_file = sys.argv[2]
    shared_dir = sys.argv[3]
    
    peer = Peer(address, port, neighbors_file, shared_dir)
    #Cria e inicia a nova thread onde o peer de entrada será executado
    threading.Thread(target=peer.start_server, daemon=True).start()

    # Exibir menu de comandos
    while True:
        print("\nEscolha um comando:")
        print("[1] Listar peers")
        print("[2] Obter peers")
        print("[3] Listar arquivos locais")
        print("[4] Buscar arquivos")
        print("[5] Exibir estatisticas")
        print("[6] Alterar tamanho de chunk")
        print("[9] Sair")
        
        opcao = input("> ")
        #Lista de Peers
        if opcao == "1":
            print("Lista de peers:")
            print("     [0] Voltar para o menu anterior")
            #Converte para lista para acessar os enderecos pelos indices
            peers_list = list(peer.neighbors.items())
            for idx, (peer_address, status) in enumerate(peers_list, start=1):
                print(f"     [{idx}] {peer_address} {status}")

            opcao = input("> ")
            if opcao == "0":
                pass #Volta para o início do loop
            else:
                try:
                    opcao = int(opcao) #Converte para inteiro para fazer a comparacao abaixo
                    if 1 <= opcao <= len(peers_list): #O numero de vizinhos varia
                        peer_address = peers_list[opcao-1][0] #Obtem o endereco do peer
                        dest_ip, dest_port = peer_address.split(":")
                        peer.send_message(dest_ip, dest_port, "HELLO")
                    else:
                        print("Opção inválida!")
                except ValueError:
                    print("Entrada inválida, digite um número!")

        #Obter Peers
        elif opcao == "2":
            #Encaminha GET_PEERS para todos os vizinhos
            for peer_address in peer.neighbors.keys():
                dest_ip, dest_port = peer_address.split(":")
                peer.send_message(dest_ip, dest_port, "GET_PEERS")

        #Lista arquivos locais do diretorio
        elif opcao == "3":
            arquivos = os.listdir(shared_dir)
            #Se há arquivos no diretório
            if arquivos:
                for arquivo in arquivos:
                    print(arquivo)
            else:
                print("Nenhum arquivo encontrado no diretório compartilhado")

        elif (opcao == "4" or opcao == "5" or opcao == "6"):
            print("Comandos 4, 5 e 6 serão implementados em partes posteriores do EP...")

        elif opcao == "9":
            #Percorre a lista de peers conhecidos
            for peer_address, status in peer.neighbors.items():
                if status == "ONLINE":
                    dest_ip, dest_port = peer_address.split(":")
                    peer.send_message(dest_ip, dest_port, "BYE")  # Envia a mensagem BYE

            print("Saindo...")
            sys.exit(0) #Encerra o programa




    

