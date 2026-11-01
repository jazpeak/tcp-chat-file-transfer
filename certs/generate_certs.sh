#!/bin/bash
set -e

# Generate CA key and certificate
openssl genrsa -out certs/ca.key 2048
openssl req -x509 -new -nodes -key certs/ca.key -sha256 -days 365 -out certs/ca.crt \
    -subj "/CN=MyRootCA"

# Generate server key and CSR
openssl genrsa -out certs/server.key 2048
openssl req -new -key certs/server.key -out certs/server.csr \
    -subj "/CN=localhost"

# Add SAN extension so python ssl verification succeeds on localhost
cat > certs/san.cnf <<EOF
subjectAltName = DNS:localhost, IP:127.0.0.1
EOF

# Sign server certificate with CA
openssl x509 -req -in certs/server.csr -CA certs/ca.crt -CAkey certs/ca.key -CAcreateserial \
    -out certs/server.crt -days 365 -sha256 -extfile certs/san.cnf

# Generate client key pair for End-to-End Encryption (E2EE)
openssl genrsa -out certs/client.key 2048
openssl rsa -in certs/client.key -pubout -out certs/client.pub

# Cleanup temp files
rm -f certs/server.csr certs/san.cnf certs/ca.srl
echo "Certificates and key pairs generated successfully in certs/"
