#!/bin/bash
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()  { echo -e "${CYAN}ℹ  ${RESET}$*"; }
ok()    { echo -e "${GREEN}✔  ${RESET}$*"; }
warn()  { echo -e "${YELLOW}⚠  ${RESET}$*" >&2; }
err()   { echo -e "${RED}✘  ${RESET}$*" >&2; exit 1; }
step()  { echo -e "\n${BOLD}══ $* ══${RESET}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${ROOT}"

VERSION="${1:-$(git describe --tags --always 2>/dev/null || echo 'dev')}"
VERSION="${VERSION#v}"
ARCH="$(uname -m)"
APPIMAGE_NAME="TPGK-${VERSION}-${ARCH}.AppImage"
APPIMAGETOOL_VERSION="1.9.1"
APPIMAGETOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/${APPIMAGETOOL_VERSION}/appimagetool-${ARCH}.AppImage"

info "Root progetto: ${ROOT}"
info "Versione: ${VERSION}  |  Arch: ${ARCH}"
info "Output:   dist/${APPIMAGE_NAME}"

step "Verifica ambiente"
command -v python3 >/dev/null 2>&1 || err "python3 non trovato."
ok "python3: $(python3 --version)"

step "Preparazione virtualenv (.venv-build/)"
VENV_DIR="${ROOT}/.venv-build"
python3 -m venv --system-site-packages "${VENV_DIR}" 2>/dev/null || \
    err "python3 -m venv fallito. Installa python3-venv."
source "${VENV_DIR}/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet requests psutil pyinstaller
ok "Dipendenze installate."

step "Build PyInstaller (--onedir)"
rm -rf build/ dist/tpgk/ dist/tpgk.AppDir/
python3 -m PyInstaller packaging/appimage/tpgk.spec --noconfirm
ok "PyInstaller completato: dist/tpgk/"

step "Assemblaggio AppDir"
bash packaging/appimage/make-appdir.sh
ok "AppDir pronto: dist/tpgk.AppDir/"

step "Ricerca appimagetool"
APPIMAGETOOL=""
if command -v appimagetool >/dev/null 2>&1; then
    APPIMAGETOOL="appimagetool"
elif [[ -f "packaging/appimage/appimagetool-${ARCH}.AppImage" ]]; then
    APPIMAGETOOL="packaging/appimage/appimagetool-${ARCH}.AppImage"
else
    warn "Scaricamento appimagetool..."
    wget -q "${APPIMAGETOOL_URL}" \
        -O "packaging/appimage/appimagetool-${ARCH}.AppImage"
    chmod +x "packaging/appimage/appimagetool-${ARCH}.AppImage"
    APPIMAGETOOL="packaging/appimage/appimagetool-${ARCH}.AppImage"
fi
ok "appimagetool: ${APPIMAGETOOL}"
if [[ "${ARCH}" == "x86_64" ]]; then
    TOOL_PATH="${APPIMAGETOOL}"
    [[ "${TOOL_PATH}" == "appimagetool" ]] && TOOL_PATH="$(command -v appimagetool)"
    [[ "${TOOL_PATH}" != /* ]] && TOOL_PATH="${ROOT}/${TOOL_PATH}"
    if ! printf '%s  %s\n' "${APPIMAGETOOL_SHA256}" "${TOOL_PATH}" | sha256sum --check --strict; then
        if [[ "${TOOL_PATH}" == "${ROOT}/packaging/appimage/appimagetool-${ARCH}.AppImage" ]]; then
            warn "appimagetool locale non corrisponde alla release ${APPIMAGETOOL_VERSION}; lo riscarico."
            wget -q "${APPIMAGETOOL_URL}" -O "${TOOL_PATH}"
            chmod +x "${TOOL_PATH}"
            printf '%s  %s\n' "${APPIMAGETOOL_SHA256}" "${TOOL_PATH}" | sha256sum --check --strict
        else
            err "appimagetool non corrisponde alla release verificata ${APPIMAGETOOL_VERSION}."
        fi
    fi
fi

step "Creazione AppImage"
mkdir -p dist
export ARCH
"${APPIMAGETOOL}" dist/tpgk.AppDir "dist/${APPIMAGE_NAME}"

echo ""
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
echo -e "${GREEN}  AppImage creata: dist/${APPIMAGE_NAME}${RESET}"
echo -e "  Dimensione: $(du -sh "dist/${APPIMAGE_NAME}" | cut -f1)"
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
