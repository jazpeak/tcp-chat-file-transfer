import socket
import ssl
import threading
import os
import hashlib

HOST = '127.0.0.1'
PORT = 5000
SERVER_DIR = 'server_data'
CERT_FILE = 'certs/server.crt'
KEY_FILE = 'certs/server.key'

if not os.path.exists(SERVER_DIR):
    os.makedirs(SERVER_DIR)

clients = {}
passwords = {}
pubkeys = {}
lock = threading.Lock()

def hash_pwd(pwd, salt):
    return hashlib.sha256((pwd + salt).encode('utf-8')).hexdigest()

def get_file_hash(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(4096):
            h.update(chunk)
    return h.hexdigest()

def handle_client(user, addr):
    print("New connection from", addr)
    username = None
    buf = b''
    
    while True:
        try:
            while b'\n' not in buf:
                chunk = user.recv(4096)
                if not chunk:
                    break
                buf += chunk
            if b'\n' not in buf:
                break
                
            line, buf = buf.split(b'\n', 1)
            data = line.decode('utf-8', errors='replace').strip()
            if not data:
                continue
                
            parts = data.split(' ')
            cmd = parts[0].upper()
            
            #authentication
            if cmd == 'LOGIN':
                req_user = parts[1]
                client_hash = parts[2]
                client_pubkey = parts[3] if len(parts) > 3 else ""
                
                lock.acquire()
                if req_user in clients:
                    user.send("ERROR : User is already logged in\n".encode('utf-8'))
                elif req_user in passwords:
                    salt, stored_hash = passwords[req_user]
                    if hash_pwd(client_hash, salt) == stored_hash:
                        clients[req_user] = user
                        pubkeys[req_user] = client_pubkey
                        username = req_user
                        user.send("OK LOGIN\n".encode('utf-8'))
                        print(username, "logged in")
                    else:
                        user.send("ERROR : Wrong password.\n".encode('utf-8'))
                else:
                    # new user registration with salt
                    salt = os.urandom(16).hex()
                    passwords[req_user] = (salt, hash_pwd(client_hash, salt))
                    clients[req_user] = user
                    pubkeys[req_user] = client_pubkey
                    username = req_user
                    user.send("OK LOGIN\n".encode('utf-8'))
                    print(username, "registered and logged in")
                lock.release()
                
            elif username is None:
                user.send("ERROR : Please login first\n".encode('utf-8'))

            # key exchange for end-to-end encryption
            elif cmd == 'GETKEY':
                target = parts[1]
                lock.acquire()
                pkey = pubkeys.get(target)
                lock.release()
                if pkey:
                    user.send(f"KEY {target} {pkey}\n".encode('utf-8'))
                else:
                    user.send("ERROR : User not found\n".encode('utf-8'))

            #command handlings    
            elif cmd == 'MSG':
                target = parts[1]
                # encrypted payload relayed without server decrypting
                msg_payload = " ".join(parts[2:])
                
                lock.acquire()
                if target in clients:
                    target_user = clients[target]
                    target_user.send(f"FROM {username} {msg_payload}\n".encode('utf-8'))
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
                filename = os.path.basename(parts[1])
                filesize = int(parts[2])
                expected_hash = parts[3]
                user.send("OK UPLOAD_READY\n".encode('utf-8'))
                
                filepath = os.path.join(SERVER_DIR, filename)
                temp_path = filepath + ".tmp"
                f = open(temp_path, 'wb')
                hasher = hashlib.sha256()
                received = 0

                if buf:
                    chunk = buf[:filesize]
                    buf = buf[filesize:]
                    f.write(chunk)
                    hasher.update(chunk)
                    received += len(chunk)

                while received < filesize:
                    chunk = user.recv(min(4096, filesize - received))
                    if not chunk:
                        break
                    f.write(chunk)
                    hasher.update(chunk)
                    received += len(chunk)
                f.close()

                # check integrity
                if hasher.hexdigest() == expected_hash:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    os.rename(temp_path, filepath)
                    user.send("OK UPLOAD_VERIFIED\n".encode('utf-8'))
                    print(username, "uploaded", filename, "(integrity OK)")
                else:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    user.send("ERROR : File integrity check failed\n".encode('utf-8'))
                    print("Integrity check failed for upload:", filename)
                
            elif cmd == 'DOWNLOAD':
                filename = os.path.basename(parts[1])
                filepath = os.path.join(SERVER_DIR, filename)
                if os.path.exists(filepath):
                    filesize = os.path.getsize(filepath)
                    file_hash = get_file_hash(filepath)
                    user.send(f"FILE {filename} {filesize} {file_hash}\n".encode('utf-8'))
                    
                    f = open(filepath, 'rb')
                    while True:
                        chunk = f.read(4096)
                        if not chunk:
                            break
                        user.send(chunk)
                    f.close()
                    print(username, "downloaded", filename)
                else:
                    user.send("ERROR : File not found\n".encode('utf-8'))
                    
            elif cmd == 'SEND':
                target = parts[1]
                filename = os.path.basename(parts[2])
                filesize = int(parts[3])
                file_hash = parts[4]
                enc_key = parts[5] if len(parts) > 5 else ""
                
                lock.acquire()
                target_user = clients.get(target)
                lock.release()
                
                if target_user:
                    user.send("OK SEND_READY\n".encode('utf-8'))
                    target_user.send(f"INCOMING {username} {filename} {filesize} {file_hash} {enc_key}\n".encode('utf-8'))
                    
                    received = 0
                    if buf:
                        chunk = buf[:filesize]
                        buf = buf[filesize:]
                        target_user.send(chunk)
                        received += len(chunk)

                    while received < filesize:
                        chunk = user.recv(min(4096, filesize - received))
                        if not chunk:
                            break
                        target_user.send(chunk)
                        received += len(chunk)
                    print(f"Relayed {filename} from {username} to {target} (E2EE encrypted)")
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
        if username in pubkeys:
            del pubkeys[username]
        lock.release()
        print(username, "disconnected")
    user.close()

def main():
    # setup TLS context
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    print("Secure server started on", PORT)
    #server loop
    while True:
        try:
            user, addr = server.accept()
            # wrap socket with TLS
            secure_user = context.wrap_socket(user, server_side=True)
            t = threading.Thread(target=handle_client, args=(secure_user, addr))
            t.start()
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    main()
