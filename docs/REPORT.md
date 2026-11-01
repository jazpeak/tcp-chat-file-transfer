# Technical Report: Secure Multi-Client File Transfer

**Author:** Jazl Anwar  
**Networking:** TCP Sockets with Transport Layer Security (TLS)

## 1. Introduction

This project implements a secure multi-client chat and file transfer system featuring transport-layer encryption, certificate-based authentication, salted credential protection, cryptographic file integrity verification, and relayed end-to-end encryption. The core implementation relies on Python's standard networking and security libraries alongside cryptography primitives.

## 2. Design and Security Architecture

### 2.1 Public Key Infrastructure (PKI) & Certificates
The system implements a Certificate Authority (CA) hierarchy using OpenSSL:
1. **Root CA (`certs/ca.crt`):** A self-signed Certificate Authority certificate used to sign server credentials.
2. **Server Certificate (`certs/server.crt`):** An X.509 certificate signed by the Root CA, configured with Subject Alternative Names (`DNS:localhost`, `IP:127.0.0.1`).
3. **Client-side Verification:** The client initializes `ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)` with `ca.crt` loaded into its trusted CA store. It enforces `check_hostname = True` and `verify_mode = ssl.CERT_REQUIRED`. Connections to servers presenting invalid, untrusted, or expired certificates are rejected before any application data is sent.

### 2.2 Transport Layer Security (TLS) & Concurrency
The server uses a thread-per-connection architecture:
- The main thread accepts incoming TCP connections on `127.0.0.1:5000`.
- Each raw socket is wrapped with `ssl_context.wrap_socket(client_sock, server_side=True)`.
- TLS handshake errors (e.g. untrusted client or probe) are isolated and handled gracefully without crashing the server.
- Each client thread maintains an independent secure TLS session. All chat text (`MSG`, `BROADCAST`) and binary files (`UPLOAD`, `DOWNLOAD`, `SEND`) pass through the TLS tunnel as encrypted TLS Application Data records.

### 2.3 Authentication Security
- **No Plaintext Passwords in Transit:** When the user enters their password, the client computes `SHA-256(password)` before sending `LOGIN <username> <pw_hash>`. Even inside the TLS tunnel, raw passwords are never transmitted.
- **No Plaintext Passwords in Storage:** The server generates a random 16-byte cryptographic salt (`os.urandom(16).hex()`) on initial registration. Credentials are saved in memory as `(salt, SHA-256(pw_hash + salt))`.
- **Validation:** Invalid passwords and duplicate sessions are rejected with explicit error responses.

### 2.4 Cryptographic Digests & File Integrity Verification
- **Digest Computation:** Senders calculate the SHA-256 checksum of any file prior to transmission (`UPLOAD`, `DOWNLOAD`, `SEND`).
- **Framing Extension:** Headers convey the file size and the expected hex digest (e.g. `UPLOAD photo.jpg 20480 <sha256>`).
- **Receiver Verification:** Receivers update a running SHA-256 digest in chunks during transfer. Once the byte stream is complete, the receiver compares the computed digest with the expected digest:
  - If identical: the transfer is verified and written to disk.
  - If mismatched: the corrupted file is deleted or rejected, and an integrity failure warning is emitted.

### 2.5 End-to-End Encryption (E2EE) for Relayed Communications
For private messaging (`MSG`) and peer-to-peer file transfer (`SEND`), the server functions strictly as a relay:
- **Client Key Pairs:** Each client generates an RSA-2048 public/private key pair upon startup and registers the public key with the server on `LOGIN`.
- **Key Discovery:** Senders query `GETKEY <user>` to fetch the recipient's public key.
- **Hybrid Encryption:** Senders generate a one-time 256-bit AES session key, encrypt it with the recipient's RSA public key (OAEP with SHA-256), and encrypt the message text or file content using **AES-256-GCM**.
- **Relay Blindness:** The server receives only ciphertext blobs and forwards them. The server possesses no private key for the recipient and therefore cannot decrypt or inspect private communications.
- **Recipient Decryption:** Only the intended recipient can decrypt the session key using their private key and decrypt the payload.

## 3. Wireshark Packet Inspection Analysis

When monitoring the loopback interface (`lo` on port 5000) using Wireshark or `tcpdump`:
1. **TCP Handshake:** Standard `SYN`, `SYN-ACK`, `ACK` on port 5000.
2. **TLS Handshake:** `Client Hello`, `Server Hello`, `Certificate`, `Server Key Exchange`, and `Finished`.
3. **Encrypted Records:** All subsequent packets appear strictly as `Application Data Protocol: TLSv1.3` (or TLSv1.2).
4. **Data Privacy:** Neither login commands (`LOGIN`), user chat messages (`MSG`, `BROADCAST`), nor binary file contents appear in plaintext.

## 4. Evaluation and Benchmarks

The automated test suite (`tests/benchmark.py`) verifies security and measures performance:

| Test Case | Description | Result (Localhost) |
|---|---|---|
| **Test 1: RTT** | Single-client round-trip time over TLS | ~0.54 ms |
| **Test 2: Broadcast** | Average latency across 5 concurrent clients | ~0.65 ms |
| **Test 3: 100 KB Download** | 10 concurrent clients downloading 100 KB + SHA-256 verification | ~0.94 MB/s (10/10 verified) |
| **Test 3: 1 MB Download** | 10 concurrent clients downloading 1 MB + SHA-256 verification | ~9.30 MB/s (10/10 verified) |
| **Test 3: 10 MB Download** | 10 concurrent clients downloading 10 MB + SHA-256 verification | ~111.29 MB/s (10/10 verified) |
| **Test 4: Auth Security** | Rejection of wrong passwords & duplicate sessions | PASS |
| **Test 5: Cert Verification** | Rejection of untrusted server certificates | PASS (`SSLCertVerificationError`) |
| **Test 6: Tamper Detection** | Intentional byte corruption during upload | PASS (Server detected & rejected) |
| **Test 7: End-to-End Encryption** | Relayed message encrypted with RSA+AES-GCM; server cannot decrypt | PASS (Decrypted only by recipient) |
