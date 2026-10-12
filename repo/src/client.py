import socket
import threading
import os
import sys
import time
import shutil

HOST = '127.0.0.1'
PORT = 5000

def receive_messages(sock, client_dir):
    # Bytes received but not yet consumed. TCP may deliver a text header and the
    # first bytes of file data in the same recv(), so we parse from a buffer.
    buf = b''
    while True:
        try:
            while b'\n' not in buf:
                data = sock.recv(4096)
                if not data:
                    return
                buf += data

            line, buf = buf.split(b'\n', 1)
            line = line.decode('utf-8', errors='replace')
            if not line:
                continue

            parts = line.split(' ')
            cmd = parts[0]

            if cmd in ('FILE', 'INCOMING'):
                if cmd == 'FILE':
                    filename = parts[1]
                    filesize = int(parts[2])
                else:
                    filename = parts[2]
                    filesize = int(parts[3])

                print(f"\nReceiving file {filename} ({filesize} bytes)...")

                # Use basename so a remote filename can't escape client_dir
                filepath = os.path.join(client_dir, os.path.basename(filename))
                received = 0
                with open(filepath, 'wb') as f:
                    # First consume any file bytes already sitting in the buffer
                    if buf:
                        chunk, buf = buf[:filesize], buf[filesize:]
                        f.write(chunk)
                        received += len(chunk)
                    while received < filesize:
                        chunk = sock.recv(min(4096, filesize - received))
                        if not chunk:
                            break
                        f.write(chunk)
                        received += len(chunk)
                print(f"File {filename} received and saved in {client_dir}/")
            else:
                print("\nServer:", line)

        except Exception:
            # Normal on shutdown (socket closed); nothing useful to report
            break

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    
    user = input("Username: ")
    pwd = input("Password: ")
    
    sock.send(f"LOGIN {user} {pwd}\n".encode('utf-8'))
    
    resp = sock.recv(1024).decode('utf-8')
    print("Server:", resp.strip())
    if "ERROR" in resp:
        return
        
    # Auto-create a folder just for this client
    client_dir = f"{user}_data"
    if not os.path.exists(client_dir):
        os.makedirs(client_dir)
    print(f"Created private folder: {client_dir}/")
        
    t = threading.Thread(target=receive_messages, args=(sock, client_dir))
    t.daemon = True # Allows thread to die cleanly when main program exits
    t.start()
    
    print("Commands: MSG user text, BROADCAST text, LIST, UPLOAD file, DOWNLOAD file, SEND user file, LOGOUT")
    
    try:
        while True:
            cmd = input("Enter command: ")
            if not cmd:
                continue
                
            parts = cmd.split(' ')
            command = parts[0].upper()
            
            if command == 'UPLOAD':
                filename = parts[1]
                filepath = os.path.join(client_dir, filename)
                if os.path.exists(filepath):
                    filesize = os.path.getsize(filepath)
                    
                    sock.send(f"UPLOAD {filename} {filesize}\n".encode('utf-8'))
                    time.sleep(0.5) 
                    
                    f = open(filepath, 'rb')
                    while True:
                        chunk = f.read(1024)
                        if not chunk:
                            break
                        sock.send(chunk)
                    f.close()
                    print(f"Uploaded {filename} from {client_dir}/")
                else:
                    print(f"File not found in {client_dir}/. Please put it there first!")
                    
            elif command == 'SEND':
                target = parts[1]
                filename = parts[2]
                filepath = os.path.join(client_dir, filename)
                if os.path.exists(filepath):
                    filesize = os.path.getsize(filepath)
                    sock.send(f"SEND {target} {filename} {filesize}\n".encode('utf-8'))
                    time.sleep(0.5)
                    f = open(filepath, 'rb')
                    while True:
                        chunk = f.read(1024)
                        if not chunk:
                            break
                        sock.send(chunk)
                    f.close()
                    print(f"Sent {filename} from {client_dir}/ to {target}")
                else:
                    print(f"File not found in {client_dir}/. Please put it there first!")
                    
            elif command == 'LOGOUT':
                sock.send("LOGOUT\n".encode('utf-8'))
                break
                
            else:
                sock.send((cmd + '\n').encode('utf-8'))
                if command == 'MSG':
                    print(f"Message sent.")
                    
    except KeyboardInterrupt:
        # Catch Ctrl+C so we can still run the cleanup code below
        pass 
    finally:
        print(f"\nCleaning up and deleting {client_dir}/...")
        if os.path.exists(client_dir):
            shutil.rmtree(client_dir)
        sock.close()

if __name__ == "__main__":
    main()
