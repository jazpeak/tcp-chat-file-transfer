# Secure Multi-Client Chat & File Transfer over TLS

A multi-threaded client–server system in Python supporting private messaging, broadcast, secure server storage, and relayed peer-to-peer file transfer over raw TCP sockets wrapped with **Transport Layer Security (TLS)**.

This project provides a robust, secure communication system with transport-layer encryption, certificate-based server verification, salted credential storage, cryptographic file integrity checks using SHA-256 message digests, and hybrid client-to-client end-to-end encryption.

---

## Features

- **TLS Transport Encryption:** Full cryptographic transport security using Python's `ssl` module; all text commands, messages, and binary file streams are encrypted on the wire.
- **X.509 Certificate Verification:** Server is configured with a digital certificate signed by a Certificate Authority (CA) with Subject Alternative Names (SAN); clients strictly verify certificate authenticity and hostname (`ssl.CERT_REQUIRED`), rejecting untrusted certificates.
- **End-to-End Encryption (E2EE):** For relayed client-to-client operations (`MSG` and `SEND`), clients use hybrid **RSA-2048 + AES-256-GCM**. The server functions strictly as a relay and cannot decrypt or read private messages or files.
- **Secure Authentication:** Passwords are pre-hashed client-side (SHA-256) prior to transmission and stored server-side with unique cryptographic salts (`os.urandom(16).hex()`).
- **Cryptographic File Integrity:** Senders compute SHA-256 digests before file transmission; receivers recalculate digests in real-time to detect corruption or tampering.
- **Tamper Detection Demonstration:** Automated detection and rejection of modified or corrupted files.
- **Concurrent Clients:** Thread-per-connection architecture supporting concurrent messaging and downloads (tested with 100 KB, 1 MB, 10 MB files).
- **Wireshark Verified:** Zero plaintext leakage; all network traffic appears as TLS Application Data records.

---

## Tech Stack

Python 3 · `socket` · `ssl` · `threading` · `hashlib` · `cryptography` · `OpenSSL`

---

## Project Structure

```
.
├── certs/
│   ├── generate_certs.sh # OpenSSL script to generate CA, Server, and Client keys
│   ├── ca.crt            # Root Certificate Authority certificate
│   ├── ca.key            # Root CA private key
│   ├── server.crt        # Server digital certificate (signed by CA, with SAN)
│   ├── server.key        # Server private key
│   ├── client.crt / .pub # OpenSSL client key pair for E2EE
│   └── client.key        # Client private key
├── src/
│   ├── server.py         # Multi-threaded TLS TCP server
│   └── client.py         # Interactive TLS client with background listener & E2EE
├── tests/
│   └── benchmark.py      # Automated security & performance test suite
└── docs/
    ├── PROTOCOL.md       # Secure application-layer protocol specification
    └── REPORT.md         # Technical architecture & security report
```

---

## Quick Start

### 1. Generate Certificates (Open-Source OpenSSL)

Sample certificates and keys are pre-generated in `certs/`. To regenerate them using OpenSSL:

```bash
chmod +x certs/generate_certs.sh
./certs/generate_certs.sh
```

This creates:
* A Root Certificate Authority (`certs/ca.crt`, `certs/ca.key`).
* A Server Certificate (`certs/server.crt`, `certs/server.key`) signed by the Root CA with SAN (`DNS:localhost`, `IP:127.0.0.1`).
* Client RSA Key Pair (`certs/client.key`, `certs/client.pub`) for End-to-End Encryption.

### 2. Start the Secure Server

```bash
python3 src/server.py
```
*Listens on `127.0.0.1:5000` with TLS enabled.*

### 3. Start Clients

In separate terminal windows:

```bash
python3 src/client.py
```

Enter a username and password when prompted (new usernames are automatically registered on first login).

#### Client Commands

| Command | Description |
|---|---|
| `MSG <user> <text>` | Send a private encrypted message |
| `BROADCAST <text>` | Broadcast an encrypted message to all online users |
| `LIST` | List active users |
| `UPLOAD <file>` | Securely upload a file with SHA-256 integrity check to server |
| `DOWNLOAD <file>` | Download a file from server with SHA-256 verification |
| `SEND <user> <file>` | Send a file to another client (relayed through server with integrity verification) |
| `LOGOUT` | Disconnect gracefully |

*Each client receives an isolated folder (e.g. `alice_data/`) created on login. Files to upload/send should be placed there; received files land there automatically.*

---

## Verification & Testing

### Running Automated Test Suite

With the server running, execute:

```bash
python3 tests/benchmark.py
```

The test suite automatically executes and asserts:
1. **Single-Client RTT:** Round-trip latency over TLS.
2. **Encrypted Broadcast Latency:** Broadcast delay across 5 concurrent clients.
3. **Concurrent Download Throughput (10 Clients):** Transfers and verifies SHA-256 integrity for **100 KB, 1 MB, and 10 MB** files.
4. **Authentication Security:** Verifies rejection of wrong passwords, rejection of duplicate logins, and registration with salted hashes.
5. **Certificate Verification:** Attempts connection without CA trust and verifies that `ssl.SSLCertVerificationError` correctly rejects the untrusted certificate.
6. **Tamper Detection Demonstration:** Uploads a test file with an altered byte stream and asserts that the server detects the digest mismatch, emits an integrity failure alert, and rejects the corrupted file.

### Sample Test Results (Localhost)

```
Ensure the server is running on 127.0.0.1:5000 before running tests.

--- Running Test 1: RTT (1 Client over TLS) ---
RTT: 0.48 ms

--- Running Test 2: Broadcast to 5 Clients ---
Average response time across 5 clients: 0.85 ms

--- Running Test 3: Server Throughput (10 Clients, 100 KB) ---
Generating test file dummy_100KB.bin (102400 bytes)...
Total Data Transferred: 0.98 MB
Total Duration: 1.07 seconds
Server Throughput: 0.91 MB/s
Verified files: 10/10 clients matched SHA-256 hash

--- Running Test 3: Server Throughput (10 Clients, 1 MB) ---
Generating test file dummy_1MB.bin (1048576 bytes)...
Total Data Transferred: 10.00 MB
Total Duration: 1.04 seconds
Server Throughput: 9.64 MB/s
Verified files: 10/10 clients matched SHA-256 hash

--- Running Test 3: Server Throughput (10 Clients, 10 MB) ---
Generating test file dummy_10MB.bin (10485760 bytes)...
Total Data Transferred: 100.00 MB
Total Duration: 1.18 seconds
Server Throughput: 85.04 MB/s
Verified files: 10/10 clients matched SHA-256 hash

--- Running Test 4: Authentication Security ---
Registration and login: OK LOGIN
Duplicate login attempt: ERROR : User is already logged in
Wrong password attempt: ERROR : Wrong password.
Re-login with correct password: OK LOGIN

--- Running Test 5: Certificate Verification ---
Certificate verification correctly rejected untrusted server.

--- Running Test 6: File Integrity & Tamper Detection ---
Sending UPLOAD with original hash 8fddf31e8c... but corrupted bytes...
Server response: ERROR : File integrity check failed

--- Running Test 7: End-to-End Encryption (E2EE) between Clients ---
Decrypted message at Bob: 'Classified end-to-end secret'
E2EE Verification Successful: Server only relayed ciphertext; Bob decrypted the secret!
```

---

## Wireshark Packet Inspection Guide

To verify that network traffic contains no plaintext:
1. Open **Wireshark** and select the loopback interface (`lo` on Linux).
2. Apply the display filter:
   ```
   tcp.port == 5000
   ```
3. Start capturing and run `python3 src/client.py` (send messages, broadcast, and transfer files).
4. Observe the capture:
   - Initial TCP 3-way handshake (`SYN`, `SYN-ACK`, `ACK`).
   - TLS Handshake records (`Client Hello`, `Server Hello`, `Certificate`, `Key Exchange`).
   - All subsequent messaging, chat text, passwords, and file transfers appear strictly as **`Application Data Protocol: TLSv1.3`** or **`TLSv1.2`**.
   - Searching packet bytes for usernames, passwords, or file contents yields zero plaintext matches.



## Author

Jazl Anwar

## License

[MIT](LICENSE)
