#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 1 ]; then
  printf 'Usage: sudo %s mqtt-server-dns-or-ip\n' "$0" >&2
  exit 2
fi
server_name="$1"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
deploy_dir="$(cd "$script_dir/.." && pwd)"
tls_dir="$deploy_dir/tls"
mkdir -p "$tls_dir"
umask 077
openssl genrsa -out "$tls_dir/ca.key" 4096
openssl req -x509 -new -nodes -key "$tls_dir/ca.key" -sha256 -days 3650 \
  -subj "/CN=Dioneya EVT CA" -out "$tls_dir/ca.crt"
openssl genrsa -out "$tls_dir/server.key" 2048
openssl req -new -key "$tls_dir/server.key" -subj "/CN=$server_name" -out "$tls_dir/server.csr"
printf 'subjectAltName=DNS:%s\nextendedKeyUsage=serverAuth\n' "$server_name" > "$tls_dir/server.ext"
openssl x509 -req -in "$tls_dir/server.csr" -CA "$tls_dir/ca.crt" -CAkey "$tls_dir/ca.key" \
  -CAcreateserial -out "$tls_dir/server.crt" -days 825 -sha256 -extfile "$tls_dir/server.ext"
for client in bridge station01 station02 station03 station04; do
  openssl genrsa -out "$tls_dir/$client.key" 2048
  openssl req -new -key "$tls_dir/$client.key" -subj "/CN=$client" -out "$tls_dir/$client.csr"
  printf 'extendedKeyUsage=clientAuth\n' > "$tls_dir/$client.ext"
  openssl x509 -req -in "$tls_dir/$client.csr" -CA "$tls_dir/ca.crt" -CAkey "$tls_dir/ca.key" \
    -CAcreateserial -out "$tls_dir/$client.crt" -days 825 -sha256 -extfile "$tls_dir/$client.ext"
done
chmod 600 "$tls_dir"/*.key
printf 'TLS material created in %s\n' "$tls_dir"
printf 'Copy ca.crt, stationNN.crt and stationNN.key to the corresponding station through an offline channel.\n'
