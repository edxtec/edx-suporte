#!/usr/bin/env bash
# Licença: GNU AGPL-3.0, a mesma do RustDesk. © EDX Tecnologia em Informação Ltda.
#
# Assina executáveis Windows (Authenticode) com um certificado de assinatura
# de código emitido pela CA interna da EDX.
#
# Uso: EDX_SIGN_PFX_B64=... EDX_SIGN_PFX_PASS=... sign_internal.sh arquivo.exe [...]
#
#   EDX_SIGN_PFX_B64   .pfx (certificado + chave + cadeia) em base64
#   EDX_SIGN_PFX_PASS  senha do .pfx
#   EDX_SIGN_TSA       carimbo de tempo RFC3161 (padrão: DigiCert, público e gratuito)
#   EDX_SIGN_CHAIN     (opcional) PEM da(s) CA(s) intermediária(s), embutidas na
#                      assinatura para o Windows fechar a cadeia até a raiz da GPO
#
# Se o arquivo já tiver assinatura (ex.: Certum), esta entra como assinatura
# ANINHADA: a original continua valendo.
set -euo pipefail

[ -n "${EDX_SIGN_PFX_B64:-}" ] || { echo "EDX_SIGN_PFX_B64 ausente" >&2; exit 2; }
command -v osslsigncode >/dev/null || { echo "osslsigncode não instalado" >&2; exit 2; }
TSA="${EDX_SIGN_TSA:-http://timestamp.digicert.com}"
NAME="${EDX_SIGN_DESC:-EDX Suporte Remoto}"
URL="${EDX_SIGN_URL:-https://www.edxinfo.com.br}"

pe_signed() {
  python3 -I - "$1" <<'PY'
import struct, sys
d = open(sys.argv[1], "rb").read(4096)
pe = struct.unpack_from("<I", d, 0x3C)[0]
magic = struct.unpack_from("<H", d, pe + 24)[0]
dirs = pe + 24 + (112 if magic == 0x20B else 96)
size = struct.unpack_from("<II", d, dirs + 4 * 8)[1]
print(1 if size else 0)
PY
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
pfx="$work/cs.pfx"
printf '%s' "$EDX_SIGN_PFX_B64" | base64 -d > "$pfx"
pass="$work/pass"
printf '%s' "${EDX_SIGN_PFX_PASS:-}" > "$pass"
chain=()
if [ -n "${EDX_SIGN_CHAIN:-}" ]; then
  printf '%s\n' "$EDX_SIGN_CHAIN" > "$work/chain.pem"
  grep -q "BEGIN CERTIFICATE" "$work/chain.pem" || { echo "EDX_SIGN_CHAIN não é PEM" >&2; exit 2; }
  chain=(-ac "$work/chain.pem")
fi

for f in "$@"; do
  nest=()
  # Lê o diretório de segurança do cabeçalho PE: o osslsigncode cai com
  # -nest (e com extract-signature) num arquivo ainda sem assinatura.
  if [ "$(pe_signed "$f")" = "1" ]; then
    nest=(-nest)
  fi
  ts=()
  [ -n "$TSA" ] && [ "$TSA" != "none" ] && ts=(-ts "$TSA")
  osslsigncode sign "${nest[@]}" -pkcs12 "$pfx" -readpass "$pass" "${chain[@]}" \
    -h sha256 -n "$NAME" -i "$URL" "${ts[@]}" \
    -in "$f" -out "$f.signed" >/dev/null
  mv "$f.signed" "$f"
  echo "assinado: $f ${nest:+(aninhada)}"
done
