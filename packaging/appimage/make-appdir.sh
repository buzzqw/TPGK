#!/bin/bash
set -euo pipefail

SRC="dist/tpgk"
APPDIR="dist/tpgk.AppDir"

if [[ ! -d "$SRC" ]]; then
    echo "ERRORE: $SRC non trovato. Esegui prima PyInstaller." >&2
    exit 1
fi

echo "=== Creazione AppDir in ${APPDIR} ==="

rm -rf "${APPDIR}"
mkdir -p "${APPDIR}"

cp -r "${SRC}/." "${APPDIR}/"

cat > "${APPDIR}/tpgk.desktop" << 'DESKTOP'
[Desktop Entry]
Type=Application
Name=TPGK
Comment=Advanced terminal emulator with AI chat
Exec=AppRun
Icon=tpgk
Terminal=false
Categories=System;TerminalEmulator;
DESKTOP

python3 -c "
import struct, zlib
w, h = 256, 256
raw = b''
for y in range(h):
    raw += b'\x00' + b'\x00\x99\x33\xff' * w
def chunk(t, d):
    c = struct.pack('>I', len(d)) + t + d
    return c + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
png = b'\x89PNG\r\n\x1a\n'
png += chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
compressed = zlib.compress(raw)
png += chunk(b'IDAT', compressed)
png += chunk(b'IEND', b'')
with open('${APPDIR}/tpgk.png', 'wb') as f:
    f.write(png)
"

cat > "${APPDIR}/AppRun" << 'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export GI_TYPELIB_PATH="${HERE}/girepository-1.0:${GI_TYPELIB_PATH:-}"
export LD_LIBRARY_PATH="${HERE}/lib:${LD_LIBRARY_PATH:-}"
exec "${HERE}/tpgk" "$@"
APPRUN
chmod +x "${APPDIR}/AppRun"

echo "=== AppDir pronto: ${APPDIR} ==="
