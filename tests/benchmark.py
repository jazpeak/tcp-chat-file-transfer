import socket
import ssl
import time
import threading
import os
import hashlib
import base64
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HOST = '127.0.0.1'
PORT = 5000
SERVER_DIR = 'server_data'
CA_FILE = 'certs/ca.crt'

if not os.path.exists(SERVER_DIR):
    os.makedirs(SERVER_DIR)

test_privkey = rsa.generate_private_key(public_exponent=65537, key_size=2048)
test_pubkey_pem = test_privkey.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo
).decode('utf-8')
test_pubkey_b64 = base64.b64encode(test_pubkey_pem.encode('utf-8')).decode('utf-8')

def get_ssl_socket(ca=CA_FILE):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if ca:
        ctx.load_verify_locations(cafile=ca)
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw.connect((HOST, PORT))
    return ctx.wrap_socket(raw, server_hostname='localhost')

def connect_client(user, pwd, pubkey=test_pubkey_b64):
    s = get_ssl_socket()
    pw_hash = hashlib.sha256(pwd.encode('utf-8')).hexdigest()
    s.send(f"LOGIN {user} {pw_hash} {pubkey}\n".encode('utf-8'))
    resp = s.recv(1024).decode('utf-8')
    return s, resp

def create_dummy_file(filename, size_bytes):
    filepath = os.path.join(SERVER_DIR, filename)
    if not os.path.exists(filepath) or os.path.getsize(filepath) != size_bytes:
        print(f"Generating test file {filename} ({size_bytes} bytes)...")
        with open(filepath, 'wb') as f:
            chunk = os.urandom(min(65536, size_bytes))
            written = 0
            while written < size_bytes:
                to_write = min(len(chunk), size_bytes - written)
                f.write(chunk[:to_write])
                written += to_write
    return filepath

def run_test_1():
    print("\n--- Running Test 1: RTT (1 Client over TLS) ---")
    s, _ = connect_client("test1", "123")
    
    start = time.time()
    s.send(b"MSG nobody hello\n")
    s.recv(1024)
    end = time.time()
    
    rtt = (end - start) * 1000
    print(f"RTT: {rtt:.2f} ms")
    s.send(b"LOGOUT\n")
    s.close()

def run_test_2():
    print("\n--- Running Test 2: Broadcast to 5 Clients ---")
    
    receive_times = []
    ready_count = 0
    lock = threading.Lock()
    
    def listener(user):
        nonlocal ready_count
        s, _ = connect_client(user, "123")
        
        with lock:
            ready_count += 1
            
        while True:
            data = s.recv(1024).decode('utf-8', errors='replace')
            if "BROADCAST" in data:
                receive_times.append(time.time())
                break
        s.send(b"LOGOUT\n")
        s.close()

    threads = []
    for i in range(5):
        t = threading.Thread(target=listener, args=(f"test2_{i}",))
        t.start()
        threads.append(t)
        
    while ready_count < 5:
        time.sleep(0.05)
        
    sender, _ = connect_client("sender", "123")
    
    start_time = time.time()
    sender.send(b"BROADCAST test message\n")
    sender.recv(1024)
    
    for t in threads:
        t.join()
        
    sender.send(b"LOGOUT\n")
    sender.close()
    
    diffs = [(rt - start_time) * 1000 for rt in receive_times]
    avg_response = sum(diffs) / len(diffs)
    print(f"Average response time across 5 clients: {avg_response:.2f} ms")

def run_test_3(size_bytes, filename):
    size_label = f"{size_bytes // 1024} KB" if size_bytes < 1024 * 1024 else f"{size_bytes // (1024 * 1024)} MB"
    print(f"\n--- Running Test 3: Server Throughput (10 Clients, {size_label}) ---")
    filepath = create_dummy_file(filename, size_bytes)
    
    with open(filepath, 'rb') as f:
        expected_hash = hashlib.sha256(f.read()).hexdigest()
    
    start_times = []
    end_times = []
    verified = 0
    lock = threading.Lock()
    
    def downloader(user):
        nonlocal verified
        s, _ = connect_client(user, "123")
        s.send(f"DOWNLOAD {filename}\n".encode('utf-8'))

        buf = b''
        while b'\n' not in buf:
            data = s.recv(4096)
            if not data:
                return
            buf += data
        header, leftover = buf.split(b'\n', 1)
        try:
            parts = header.decode().strip().split(' ')
            filesize = int(parts[2])
            server_hash = parts[3]
        except Exception:
            print("Error parsing response:", header)
            return

        with lock:
            start_times.append(time.time())
            
        hasher = hashlib.sha256()
        received = len(leftover)
        if leftover:
            hasher.update(leftover)

        while received < filesize:
            chunk = s.recv(min(65536, filesize - received))
            if not chunk:
                break
            hasher.update(chunk)
            received += len(chunk)
            
        with lock:
            end_times.append(time.time())
            if hasher.hexdigest() == expected_hash:
                verified += 1
            
        s.send(b"LOGOUT\n")
        s.close()
        
    threads = []
    for i in range(10):
        t = threading.Thread(target=downloader, args=(f"test3_u{i}_{filename}",))
        t.start()
        threads.append(t)
        
    for t in threads:
        t.join()
        
    duration = max(end_times) - min(start_times)
    total_data_mb = (size_bytes * 10) / (1024 * 1024)
    throughput = total_data_mb / duration
    print(f"Total Data Transferred: {total_data_mb:.2f} MB")
    print(f"Total Duration: {duration:.2f} seconds")
    print(f"Server Throughput: {throughput:.2f} MB/s")
    print(f"Verified files: {verified}/10 clients matched SHA-256 hash")

def run_test_4():
    print("\n--- Running Test 4: Authentication Security ---")
    s1, r1 = connect_client("auth_user", "pass123")
    print("Registration and login:", r1.strip())
    
    # test duplicate login
    s2, r2 = connect_client("auth_user", "pass123")
    print("Duplicate login attempt:", r2.strip())
    s2.close()
    
    s1.send(b"LOGOUT\n")
    s1.close()
    time.sleep(0.1)
    
    # test wrong password
    s3, r3 = connect_client("auth_user", "wrong_pass")
    print("Wrong password attempt:", r3.strip())
    s3.close()
    
    # test valid re-login
    s4, r4 = connect_client("auth_user", "pass123")
    print("Re-login with correct password:", r4.strip())
    s4.send(b"LOGOUT\n")
    s4.close()

def run_test_5():
    print("\n--- Running Test 5: Certificate Verification ---")
    try:
        # connect without trusting our CA cert
        get_ssl_socket(ca=None)
        print("Warning: Connection succeeded without CA cert!")
    except ssl.SSLCertVerificationError:
        print("Certificate verification correctly rejected untrusted server.")

def run_test_6():
    print("\n--- Running Test 6: File Integrity & Tamper Detection ---")
    s, _ = connect_client("tamper_test_user", "123")
    
    original_data = b"original safe content"
    orig_hash = hashlib.sha256(original_data).hexdigest()
    
    corrupted_data = b"tampered bad content!"
    
    print(f"Sending UPLOAD with original hash {orig_hash[:10]}... but corrupted bytes...")
    s.send(f"UPLOAD test_tamper.txt {len(corrupted_data)} {orig_hash}\n".encode('utf-8'))
    ready = s.recv(1024).decode('utf-8')
    
    s.send(corrupted_data)
    result = s.recv(1024).decode('utf-8')
    print("Server response:", result.strip())
    s.send(b"LOGOUT\n")
    s.close()

def run_test_7():
    print("\n--- Running Test 7: End-to-End Encryption (E2EE) between Clients ---")
    bob_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    bob_pub_pem = bob_priv.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode('utf-8')
    bob_pub_b64 = base64.b64encode(bob_pub_pem.encode('utf-8')).decode('utf-8')
    
    bob_sock, _ = connect_client("bob_e2ee", "123", pubkey=bob_pub_b64)
    alice_sock, _ = connect_client("alice_e2ee", "123")
    
    # Alice requests Bob's public key from server
    alice_sock.send(b"GETKEY bob_e2ee\n")
    key_resp = alice_sock.recv(4096).decode('utf-8').strip()
    assert "KEY bob_e2ee" in key_resp
    bob_key_b64 = key_resp.split(' ')[2]
    
    # Alice encrypts a secret message using Bob's public key + AESGCM
    bob_pub = serialization.load_pem_public_key(base64.b64decode(bob_key_b64))
    session_key = AESGCM.generate_key(bit_length=256)
    enc_key = bob_pub.encrypt(session_key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    enc_key_b64 = base64.b64encode(enc_key).decode('utf-8')
    
    aesgcm = AESGCM(session_key)
    nonce = os.urandom(12)
    secret_text = b"Classified end-to-end secret"
    ciphertext = nonce + aesgcm.encrypt(nonce, secret_text, None)
    ct_b64 = base64.b64encode(ciphertext).decode('utf-8')
    
    # Alice sends through server relay
    alice_sock.send(f"MSG bob_e2ee {enc_key_b64} {ct_b64}\n".encode('utf-8'))
    alice_sock.recv(1024)
    
    # Bob receives from server relay
    bob_msg = bob_sock.recv(4096).decode('utf-8').strip()
    parts = bob_msg.split(' ')
    recv_enc_key = parts[2]
    recv_ct = base64.b64decode(parts[3])
    
    # Bob decrypts with his private key
    dec_session_key = bob_priv.decrypt(base64.b64decode(recv_enc_key), padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    bob_aesgcm = AESGCM(dec_session_key)
    decrypted_text = bob_aesgcm.decrypt(recv_ct[:12], recv_ct[12:], None)
    
    print(f"Decrypted message at Bob: '{decrypted_text.decode('utf-8')}'")
    assert decrypted_text == secret_text
    print("E2EE Verification Successful: Server only relayed ciphertext; Bob decrypted the secret!")
    
    alice_sock.send(b"LOGOUT\n")
    bob_sock.send(b"LOGOUT\n")
    alice_sock.close()
    bob_sock.close()

if __name__ == "__main__":
    print("Ensure the server is running on 127.0.0.1:5000 before running tests.")
    time.sleep(1)
    run_test_1()
    run_test_2()
    # Benchmark transfer sizes: 100 KB, 1 MB, 10 MB
    run_test_3(100 * 1024, "dummy_100KB.bin")
    run_test_3(1024 * 1024, "dummy_1MB.bin")
    run_test_3(10 * 1024 * 1024, "dummy_10MB.bin")
    run_test_4()
    run_test_5()
    run_test_6()
    run_test_7()
