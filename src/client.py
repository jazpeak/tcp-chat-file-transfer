import socket
import ssl
import threading
import os
import sys
import time
import shutil
import hashlib
import base64
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HOST = '127.0.0.1'
PORT = 5000
CA_FILE = 'certs/ca.crt'

peer_keys = {}

def get_file_hash(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(4096):
            h.update(chunk)
    return h.hexdigest()

def encrypt_for_peer(peer_pubkey_b64, plaintext_bytes):
    # load peer public key
    pub_pem = base64.b64decode(peer_pubkey_b64)
    peer_pub = serialization.load_pem_public_key(pub_pem)
    
    # generate random AES-256 session key
    session_key = AESGCM.generate_key(bit_length=256)
    
    # encrypt session key with peer RSA public key
    enc_key = peer_pub.encrypt(
        session_key,
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    enc_key_b64 = base64.b64encode(enc_key).decode('utf-8')
    
    # encrypt data with AESGCM
    aesgcm = AESGCM(session_key)
    nonce = os.urandom(12)
    ciphertext = nonce + aesgcm.encrypt(nonce, plaintext_bytes, None)
    return enc_key_b64, ciphertext

def decrypt_from_peer(my_privkey, enc_key_b64, ciphertext):
    enc_key = base64.b64decode(enc_key_b64)
    session_key = my_privkey.decrypt(
        enc_key,
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    aesgcm = AESGCM(session_key)
    nonce = ciphertext[:12]
    ct = ciphertext[12:]
    return aesgcm.decrypt(nonce, ct, None)

def get_peer_key(sock, target):
    if target in peer_keys:
        return peer_keys[target]
    sock.send(f"GETKEY {target}\n".encode('utf-8'))
    for _ in range(20):
        if target in peer_keys:
            return peer_keys[target]
        time.sleep(0.05)
    return None

def receive_messages(sock, client_dir, my_privkey):
    # Bytes received but not yet consumed
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

            parts = line.strip().split(' ')
            cmd = parts[0]

            if cmd == 'KEY':
                target = parts[1]
                pubkey = parts[2]
                peer_keys[target] = pubkey

            elif cmd == 'FROM':
                sender = parts[1]
                # check if message is end-to-end encrypted
                if len(parts) >= 4:
                    enc_key_b64 = parts[2]
                    enc_msg_b64 = parts[3]
                    try:
                        ct = base64.b64decode(enc_msg_b64)
                        plain_bytes = decrypt_from_peer(my_privkey, enc_key_b64, ct)
                        print(f"\nServer: FROM {sender} {plain_bytes.decode('utf-8')}")
                    except Exception:
                        print(f"\nServer: FROM {sender} [Failed to decrypt message]")
                else:
                    msg = " ".join(parts[2:])
                    print(f"\nServer: FROM {sender} {msg}")

            elif cmd in ('FILE', 'INCOMING'):
                if cmd == 'FILE':
                    filename = parts[1]
                    filesize = int(parts[2])
                    expected_hash = parts[3]
                    enc_key_b64 = None
                else:
                    sender = parts[1]
                    filename = parts[2]
                    filesize = int(parts[3])
                    expected_hash = parts[4]
                    enc_key_b64 = parts[5] if len(parts) > 5 else None

                print(f"\nReceiving file {filename} ({filesize} bytes)...")

                filepath = os.path.join(client_dir, os.path.basename(filename))
                received = 0
                file_bytes = b''

                if buf:
                    chunk = buf[:filesize]
                    buf = buf[filesize:]
                    file_bytes += chunk
                    received += len(chunk)

                while received < filesize:
                    chunk = sock.recv(min(4096, filesize - received))
                    if not chunk:
                        break
                    file_bytes += chunk
                    received += len(chunk)

                # decrypt if end-to-end encrypted
                if enc_key_b64:
                    try:
                        file_bytes = decrypt_from_peer(my_privkey, enc_key_b64, file_bytes)
                    except Exception as e:
                        print("Decryption failed:", e)

                # write to disk
                with open(filepath, 'wb') as f:
                    f.write(file_bytes)

                # verify file integrity
                computed_hash = hashlib.sha256(file_bytes).hexdigest()
                if computed_hash == expected_hash:
                    print(f"File {filename} received and verified successfully (SHA-256 match)!")
                else:
                    print(f"Warning: Integrity check failed for {filename}!")
                print(f"Saved in {client_dir}/")
            else:
                print("\nServer:", line)

        except Exception:
            # Normal on shutdown
            break

def main():
    # generate RSA keypair for client-to-client E2EE
    my_privkey = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    my_pubkey_pem = my_privkey.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    my_pubkey_b64 = base64.b64encode(my_pubkey_pem.encode('utf-8')).decode('utf-8')

    # setup TLS with CA cert verification
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=CA_FILE)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED

    raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        raw_sock.connect((HOST, PORT))
    except ConnectionRefusedError:
        print("Could not connect to server. Make sure server.py is running on port 5000!")
        return

    try:
        sock = context.wrap_socket(raw_sock, server_hostname='localhost')
    except ssl.SSLCertVerificationError:
        print("Server certificate verification failed! Untrusted certificate.")
        return
    
    user = input("Username: ")
    pwd = input("Password: ")
    
    # hash password before sending so it is not plaintext
    hashed_pwd = hashlib.sha256(pwd.encode('utf-8')).hexdigest()
    sock.send(f"LOGIN {user} {hashed_pwd} {my_pubkey_b64}\n".encode('utf-8'))
    
    resp = sock.recv(1024).decode('utf-8')
    print("Server:", resp.strip())
    if "ERROR" in resp:
        return
        
    # Auto-create a folder just for this client
    client_dir = f"{user}_data"
    if not os.path.exists(client_dir):
        os.makedirs(client_dir)
    print(f"Created private folder: {client_dir}/")
        
    t = threading.Thread(target=receive_messages, args=(sock, client_dir, my_privkey))
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
            
            if command == 'MSG':
                if len(parts) < 3:
                    print("Usage: MSG <user> <text>")
                    continue
                target = parts[1]
                msg_text = " ".join(parts[2:])
                
                # fetch target's public key for End-to-End Encryption
                pkey = get_peer_key(sock, target)
                if pkey:
                    enc_key_b64, ct = encrypt_for_peer(pkey, msg_text.encode('utf-8'))
                    enc_msg_b64 = base64.b64encode(ct).decode('utf-8')
                    sock.send(f"MSG {target} {enc_key_b64} {enc_msg_b64}\n".encode('utf-8'))
                    print("Message sent (End-to-End Encrypted).")
                else:
                    print(f"Could not get public key for {target}. User may not be online.")

            elif command == 'SEND':
                if len(parts) < 3:
                    print("Usage: SEND <user> <filename>")
                    continue
                target = parts[1]
                filename = parts[2]
                filepath = os.path.join(client_dir, filename)
                if os.path.exists(filepath):
                    pkey = get_peer_key(sock, target)
                    if not pkey:
                        print(f"Could not get public key for {target}. User may not be online.")
                        continue
                    
                    with open(filepath, 'rb') as f:
                        plain_bytes = f.read()
                    
                    file_hash = hashlib.sha256(plain_bytes).hexdigest()
                    enc_key_b64, enc_bytes = encrypt_for_peer(pkey, plain_bytes)
                    enc_size = len(enc_bytes)
                    
                    sock.send(f"SEND {target} {filename} {enc_size} {file_hash} {enc_key_b64}\n".encode('utf-8'))
                    time.sleep(0.5)
                    
                    # stream encrypted bytes
                    sent = 0
                    while sent < enc_size:
                        chunk = enc_bytes[sent:sent+4096]
                        sock.send(chunk)
                        sent += len(chunk)
                    print(f"Sent {filename} from {client_dir}/ to {target} (End-to-End Encrypted)")
                else:
                    print(f"File not found in {client_dir}/. Please put it there first!")

            elif command == 'UPLOAD':
                filename = parts[1]
                filepath = os.path.join(client_dir, filename)
                if os.path.exists(filepath):
                    filesize = os.path.getsize(filepath)
                    file_hash = get_file_hash(filepath)
                    
                    sock.send(f"UPLOAD {filename} {filesize} {file_hash}\n".encode('utf-8'))
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

            elif command == 'DOWNLOAD':
                filename = parts[1]
                sock.send(f"DOWNLOAD {filename}\n".encode('utf-8'))

            elif command == 'LOGOUT':
                sock.send("LOGOUT\n".encode('utf-8'))
                break
                
            else:
                sock.send((cmd + '\n').encode('utf-8'))
                    
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
