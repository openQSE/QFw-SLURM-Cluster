#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cluster_root=$(cd "${script_dir}/../.." && pwd)
source "${cluster_root}/qfw-install.env"
[[ ${QFW_CONTAINER_BASE} == /* ]] || { echo 'QFW_CONTAINER_BASE must be absolute' >&2; exit 2; }
docker info >/dev/null
if [[ $(docker inspect slurmctld --format '{{.State.Running}}' 2>/dev/null || true) != true ]]; then
    (cd "${cluster_root}" && ./do_startup.sh)
fi
for target in directory nwqsim fake-iqm gateway; do
    docker exec slurmctld qfw-site-services start --target "${target}"
done
host_setup=${QFW_CONTAINER_BASE}/streamflow-chemistry
container_setup=/workspace/qfw-container-base/streamflow-chemistry
venv=/workspace/qfw-container-base/streamflow-chemistry/venv-0.2.0rc3
mkdir -p "${host_setup}"
rm -rf "${host_setup}/cwl" "${host_setup}/slurm"
cp -R "${script_dir}/tests" "${script_dir}/cwl" "${script_dir}/slurm" "${script_dir}/run.py" \
    "${script_dir}/streamflow.yml" "${script_dir}/requirements.txt" "${host_setup}/"
cp "${script_dir}/cases.yml" "${host_setup}/cases.yml"
cp "${script_dir}/local.yml" "${host_setup}/profile.yml"
if [[ ! -d ${QFW_CONTAINER_BASE}/chemistry_he ]]; then
    mkdir "${QFW_CONTAINER_BASE}/chemistry_he"
    tar -C "${cluster_root}/../chemistry_he" --exclude=.git --exclude=__pycache__ -cf - . | \
        tar -C "${QFW_CONTAINER_BASE}/chemistry_he" -xf -
fi
if ! docker exec slurmctld test -x "${venv}/bin/python"; then
    docker exec slurmctld uv venv --python python3 "${venv}"
fi
docker exec slurmctld uv pip install --python "${venv}" -r "${container_setup}/requirements.txt"
app_user=${QFW_USER:-user-a}
[[ ${app_user} != root ]] || { echo 'Use a non-root application user' >&2; exit 2; }
login_home=$(docker exec slurmctld getent passwd "${app_user}" | cut -d: -f6)
[[ ${login_home} == /workspace/home/* ]] || { echo 'User needs a shared home' >&2; exit 2; }
docker exec -i --user "${app_user}" --env "HOME=${login_home}" slurmctld bash -s <<'SSH'
set -euo pipefail
umask 077
mkdir -p "$HOME/.ssh"
if [[ ! -f $HOME/.ssh/streamflow_ed25519 ]]; then
    ssh-keygen -q -t ed25519 -N '' -f "$HOME/.ssh/streamflow_ed25519"
fi
touch "$HOME/.ssh/authorized_keys"
public_key=$(cat "$HOME/.ssh/streamflow_ed25519.pub")
grep -qxF "$public_key" "$HOME/.ssh/authorized_keys" || printf '%s\n' "$public_key" >> "$HOME/.ssh/authorized_keys"
chmod 700 "$HOME/.ssh"
chmod 600 "$HOME/.ssh/authorized_keys" "$HOME/.ssh/streamflow_ed25519"
SSH
docker exec slurmctld cat /etc/ssh/ssh_host_ed25519_key.pub | \
    docker exec -i --user "${app_user}" --env "HOME=${login_home}" slurmctld bash -c '
        set -euo pipefail
        umask 077
        read -r kind key comment
        entry="slurmctld $kind $key"
        touch "$HOME/.ssh/known_hosts"
        grep -qxF "$entry" "$HOME/.ssh/known_hosts" || printf "%s\n" "$entry" >> "$HOME/.ssh/known_hosts"
    '
docker exec --user "${app_user}" --env "HOME=${login_home}" slurmctld \
    ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -i "${login_home}/.ssh/streamflow_ed25519" slurmctld true
echo 'Ready: ./streamflow/chemistry/run-local.sh'
