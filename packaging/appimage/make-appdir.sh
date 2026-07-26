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

mkdir -p "${APPDIR}/usr/share/icons/hicolor/128x128/apps"

cat > "${APPDIR}/AppRun" << 'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export GI_TYPELIB_PATH="${HERE}/girepository-1.0:${GI_TYPELIB_PATH:-}"
export LD_LIBRARY_PATH="${HERE}/lib:${LD_LIBRARY_PATH:-}"
exec "${HERE}/tpgk" "$@"
APPRUN
chmod +x "${APPDIR}/AppRun"

echo "=== AppDir pronto: ${APPDIR} ==="
