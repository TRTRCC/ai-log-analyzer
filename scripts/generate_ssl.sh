#!/bin/bash
# ============================================================
# SSL Certificate Generation Script - 等保三HTTPS配置
# ============================================================

set -e

SSL_DIR="/etc/nginx/ssl"
CERT_FILE="$SSL_DIR/cert.pem"
KEY_FILE="$SSL_DIR/key.pem"
CA_CERT="$SSL_DIR/ca.pem"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Create SSL directory
mkdir -p "$SSL_DIR"
chmod 700 "$SSL_DIR"

log_info "Generating SSL certificates for 等保三 compliance..."

# Check if certificates already exist
if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    log_warn "Certificates already exist at $SSL_DIR"
    read -p "Do you want to regenerate them? [y/N]: " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Using existing certificates"
        exit 0
    fi
fi

# Generate private key (2048-bit for 等保三)
log_info "Generating RSA private key..."
openssl genrsa -out "$KEY_FILE" 2048
chmod 600 "$KEY_FILE"

# Generate self-signed certificate (1 year validity)
log_info "Generating self-signed certificate..."

# Get hostname or IP
HOSTNAME=$(hostname -f 2>/dev/null || hostname 2>/dev/null || echo "localhost")
IP_ADDRESS=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")

openssl req -new -x509 -days 365 -key "$KEY_FILE" -out "$CERT_FILE" \
    -subj "/C=CN/ST=Beijing/L=Beijing/O=AILogAnalyzer/OU=Security/CN=$HOSTNAME" \
    -addext "subjectAltName=DNS:$HOSTNAME,DNS:localhost,IP:$IP_ADDRESS,IP:127.0.0.1"

chmod 644 "$CERT_FILE"

log_info "Certificate generation complete!"

# Display certificate info
log_info "Certificate details:"
openssl x509 -in "$CERT_FILE" -noout -text | grep -E "Subject:|Issuer:|Not Before|Not After|Public-Key"

# Generate CA certificate (optional, for client authentication)
log_info "Generating CA certificate..."
openssl genrsa -out "$SSL_DIR/ca.key" 2048

openssl req -new -x509 -days 3650 -key "$SSL_DIR/ca.key" -out "$CA_CERT" \
    -subj "/C=CN/ST=Beijing/L=Beijing/O=AILogAnalyzer/OU=CA/CN=AILogAnalyzer-CA"

chmod 644 "$CA_CERT"
chmod 600 "$SSL_DIR/ca.key"

log_info "SSL setup complete!"
echo ""
echo "============================================"
echo "Certificate files:"
echo "  Certificate: $CERT_FILE"
echo "  Private Key: $KEY_FILE"
echo "  CA Cert:     $CA_CERT"
echo ""
echo "Certificate validity: 365 days"
echo "CA validity: 10 years"
echo ""
echo "To renew certificates in 1 year:"
echo "  Run this script again"
echo ""
echo "For production, use real CA certificates"
echo "  (e.g., Let's Encrypt or internal PKI)"
echo "============================================"

# Verify certificates
log_info "Verifying certificates..."
openssl verify -CAfile "$CA_CERT" "$CERT_FILE"

log_info "All certificates verified successfully!"