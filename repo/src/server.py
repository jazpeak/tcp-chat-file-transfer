import socket
import threading
import os

HOST = '127.0.0.1'
PORT = 5000
SERVER_DIR = 'server_data'

if not os.path.exists(SERVER_DIR):
    os.makedirs(SERVER_DIR)

clients = {}
passwords = {}
lock = threading.Lock()

def handle_client(user, addr):
    print("New connection from", addr)
    username = None
    
    while True:
        try:
            data = user.recv(1024).decode('utf-8')
            if not data:
                break
                
            parts = data.strip().split(' ')
            cmd = parts[0].upper()
            #authentication
            if cmd == 'LOGIN':
                req_user = parts[1]
                pwd = parts[2]
                
                lock.acquire()
                if req_user in clients:
                    user.send("ERROR : User is already logged in\n".encode('utf-8'))
                elif req_user in passwords and passwords[req_user] != pwd:
                    user.send("ERROR : Wrong password.\n".encode('utf-8'))
                else:
                    passwords[req_user] = pwd
                    clients[req_user] = user
                    username = req_user
                    user.send("OK LOGIN\n".encode('utf-8'))
                    print(username, "logged in")
                lock.release()
                
            elif username is None:
                user.send("ERROR : Please login first\n".encode('utf-8'))
            #command handlings    
            elif cmd == 'MSG':
                target = parts[1]
                msg = " ".join(parts[2:])
                
                lock.acquire()
                if target in clients:
                    target_user = clients[target]
                    target_user.send(f"FROM {username} {msg}\n".encode('utf-8'))
                    user.send("OK MSG\n".encode('utf-8'))
                else:
                    user.send("ERROR : User not found\n".encode('utf-8'))
                lock.release()
                
            elif cmd == 'BROADCAST':
                msg = " ".join(parts[1:])
                lock.acquire()
                for u, c in clients.items():
                    if u != username:
                        c.send(f"BROADCAST {username} {msg}\n".encode('utf-8'))
                user.send("OK BROADCAST\n".encode('utf-8'))
                lock.release()
                
            elif cmd == 'LIST':
                lock.acquire()
                current = list(clients.keys())
                lock.release()
                res =  "\n".join(current) + "\n"
                user.send(res.encode('utf-8'))
            #file transfer commands    
            elif cmd == 'UPLOAD':
                filename = parts[1]
                filesize = int(parts[2])
                user.send("OK UPLOAD_READY\n".encode('utf-8'))
                
                filepath = os.path.join(SERVER_DIR, filename)
                f = open(filepath, 'wb')
                received = 0
                while received < filesize:
                    chunk = user.recv(1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
                f.close()
                print(username, "uploaded", filename)
                
            elif cmd == 'DOWNLOAD':
                filename = parts[1]
                filepath = os.path.join(SERVER_DIR, filename)
                if os.path.exists(filepath):
                    filesize = os.path.getsize(filepath)
                    user.send(f"FILE {filename} {filesize}\n".encode('utf-8'))
                    
                    f = open(filepath, 'rb')
                    while True:
                        chunk = f.read(1024)
                        if not chunk:
                            break
                        user.send(chunk)
                    f.close()
                    print(username, "downloaded", filename)
                else:
                    user.send("ERROR : File not found\n".encode('utf-8'))
                    
            elif cmd == 'SEND':
                target = parts[1]
                filename = parts[2]
                filesize = int(parts[3])
                
                lock.acquire()
                target_user = clients.get(target)
                lock.release()
                
                if target_user:
                    user.send("OK SEND_READY\n".encode('utf-8'))
                    target_user.send(f"INCOMING {username} {filename} {filesize}\n".encode('utf-8'))
                    
                    received = 0
                    while received < filesize:
                        chunk = user.recv(1024)
                        if not chunk:
                            break
                        target_user.send(chunk)
                        received += len(chunk)
                else:
                    user.send("ERROR : User not found\n".encode('utf-8'))
                    
            elif cmd == 'LOGOUT':
                break
                
        except Exception as e:
            print("Error:", e)
            break
    #disconnecting all users after server shutdown        
    if username:
        lock.acquire()
        if username in clients:
            del clients[username]
        lock.release()
        print(username, "disconnected")
    user.close()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    print("Server started on", PORT)
    #server loop
    while True:
        user, addr = server.accept()
        t = threading.Thread(target=handle_client, args=(user, addr))
        t.start()

if __name__ == "__main__":
    main()
