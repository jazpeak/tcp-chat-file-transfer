import socket
import time
import threading
import os

HOST = '127.0.0.1'
PORT = 5000
SERVER_DIR = 'server_data'

if not os.path.exists(SERVER_DIR):
    os.makedirs(SERVER_DIR)

def create_dummy_file(filename, size_mb):
    filepath = os.path.join(SERVER_DIR, filename)
    if not os.path.exists(filepath):
        print(f"Generating {size_mb}MB dummy file (this may take a moment)...")
        with open(filepath, 'wb') as f:
            # Write in chunks to not explode RAM
            chunk = os.urandom(1024 * 1024) # 1MB chunk
            for _ in range(size_mb):
                f.write(chunk)
    return filepath

def run_test_1():
    print("\n--- Running Test 1: RTT (1 Client) ---")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((HOST, PORT))
    
    s.send(b"LOGIN test1 123\n")
    s.recv(1024)
    
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
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOST, PORT))
        s.send(f"LOGIN {user} 123\n".encode())
        s.recv(1024)
        
        with lock:
            ready_count += 1
            
        while True:
            data = s.recv(1024).decode()
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
        time.sleep(0.1)
        
    sender = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sender.connect((HOST, PORT))
    sender.send(b"LOGIN sender 123\n")
    sender.recv(1024)
    
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

def run_test_3(size_mb, filename):
    print(f"\n--- Running Test 3: Server Throughput (10 Clients, {size_mb}MB) ---")
    create_dummy_file(filename, size_mb)
    time.sleep(1)
    
    start_times = []
    end_times = []
    lock = threading.Lock()
    
    def downloader(user):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOST, PORT))
        s.send(f"LOGIN {user} 123\n".encode())
        s.recv(1024)
        
        s.send(f"DOWNLOAD {filename}\n".encode())

        # Read the header line byte-wise-safe: header and file bytes may share a recv()
        buf = b''
        while b'\n' not in buf:
            data = s.recv(4096)
            if not data:
                print("Connection closed before header")
                return
            buf += data
        header, leftover = buf.split(b'\n', 1)
        try:
            # Protocol responds with: FILE filename filesize
            filesize = int(header.decode().split(' ')[2])
        except Exception:
            print("Error parsing response:", header)
            return

        with lock:
            start_times.append(time.time())
            
        received = len(leftover)
        while received < filesize:
            # We don't save to disk to save space/time, we just read the network stream
            chunk = s.recv(65536) 
            if not chunk:
                break
            received += len(chunk)
            
        with lock:
            end_times.append(time.time())
            
        s.send(b"LOGOUT\n")
        s.close()
        
    threads = []
    for i in range(10):
        t = threading.Thread(target=downloader, args=(f"test3_u{i}_{size_mb}",))
        t.start()
        threads.append(t)
        
    for t in threads:
        t.join()
        
    if not start_times or not end_times:
        print("Test failed: No clients completed the download.")
        return
        
    global_start = min(start_times)
    global_end = max(end_times)
    duration = global_end - global_start
    
    total_data_mb = (size_mb * 10) 
    throughput = total_data_mb / duration
    print(f"Total Data Transferred: {total_data_mb} MB")
    print(f"Total Duration: {duration:.2f} seconds")
    print(f"Server Throughput: {throughput:.2f} MB/s")

if __name__ == "__main__":
    print("Ensure the server is running on 127.0.0.1:5000 before running tests.")
    time.sleep(1)
    run_test_1()
    run_test_2()
    run_test_3(1, "dummy_1MB.bin")
    run_test_3(100, "dummy_100MB.bin")
    run_test_3(1000, "dummy_1GB.bin")
