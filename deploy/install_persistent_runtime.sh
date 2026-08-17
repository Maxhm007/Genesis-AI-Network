#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${GENE_REPO_URL:-https://github.com/Maxhm007/Genesis-AI-Network.git}"
INSTALL_DIR="${GENE_INSTALL_DIR:-/opt/genesis}"
GENES="${GENE_LOGICAL_IDS:-gene-node-1}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git python3 python3-venv python3-pip ca-certificates

if ! id gene >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin gene
fi

if [[ ! -d "${INSTALL_DIR}/.git" ]]; then
  git clone "${REPO_URL}" "${INSTALL_DIR}"
else
  git -C "${INSTALL_DIR}" fetch origin main
  git -C "${INSTALL_DIR}" checkout main
  git -C "${INSTALL_DIR}" pull --ff-only origin main
fi

python3 -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip
"${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

mkdir -p "${INSTALL_DIR}/runtime"
chown -R gene:gene "${INSTALL_DIR}"

install -m 0644 "${INSTALL_DIR}/deploy/systemd/gene-continuous@.service" /etc/systemd/system/gene-continuous@.service
systemctl daemon-reload

for logical_id in ${GENES}; do
  systemctl enable --now "gene-continuous@${logical_id}.service"
done

systemctl --no-pager --full status "gene-continuous@${GENES%% *}.service" || true
