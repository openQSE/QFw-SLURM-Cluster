#!/bin/bash
#
# Forward the IQM endpoint into the SLURM cluster over an SSH tunnel to "hub".
#
# hub is the only machine with a route to the IQM system, but it has no tooling
# on it. That is fine: SSH port forwarding is implemented entirely by sshd, so
# nothing needs to be installed there -- only AllowTcpForwarding (the default).
#
# Only needed OFF the ORNL network -- on-site the endpoint resolves and routes
# directly. See IQM-ACCESS.md.
#
# Run this on the Docker host and leave it running. It binds
# 0.0.0.0:${LOCAL_PORT} so the cluster containers can reach it via the Docker
# host gateway; the companion docker-compose.iqm-tunnel.yml maps the real IQM
# hostname to that gateway inside the containers, which keeps TLS end-to-end and
# the certificate hostname valid.
#
#   ./iqm-tunnel.sh           # run the tunnel (leave open)
#   ./iqm-tunnel.sh --check   # probe it; HTTP 401 means healthy
#
# Configure by editing iqm-tunnel.env (see iqm-tunnel.env.example), or by
# exporting IQM_HOST / IQM_PORT / HUB / LOCAL_PORT in the environment.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/iqm-tunnel.env"

if [ -f "${ENV_FILE}" ]; then
    # shellcheck disable=SC1090
    . "${ENV_FILE}"
fi

IQM_HOST="${IQM_HOST:-}"
IQM_PORT="${IQM_PORT:-443}"
HUB="${HUB:-hub}"
LOCAL_PORT="${LOCAL_PORT:-8443}"
BIND_ADDR="${BIND_ADDR:-0.0.0.0}"
RETRY_DELAY="${RETRY_DELAY:-5}"

usage() {
    cat <<EOF
Usage: $(basename "$0") [--once] [--check]

Options:
  --once    Run the tunnel a single time; do not restart it if it drops
  --check   Probe the forwarded port and exit (tunnel must already be up)

Configuration (iqm-tunnel.env or environment):
  IQM_HOST    hostname of the IQM endpoint, as resolved from hub  (required)
  IQM_PORT    port of the IQM endpoint                            (default 443)
  HUB         ssh destination for the hub node                    (default hub)
  LOCAL_PORT  port to listen on locally                           (default 8443)
  BIND_ADDR   address to listen on                                (default 0.0.0.0)
EOF
}

ONCE=false
CHECK_ONLY=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --once)
            ONCE=true
            shift
            ;;
        --check)
            CHECK_ONLY=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [ -z "${IQM_HOST}" ]; then
    echo "IQM_HOST is not set. Create ${ENV_FILE} (see iqm-tunnel.env.example)" >&2
    echo "with the IQM hostname as it resolves from ${HUB}." >&2
    exit 1
fi

if ${CHECK_ONLY}; then
    echo "Probing TLS through the tunnel: https://${IQM_HOST}:${LOCAL_PORT}/"
    # Resolve the IQM name to the tunnel so SNI and cert validation use the
    # real hostname, exactly as the containers will.
    curl -sS -o /dev/null -w 'HTTP %{http_code}, TLS to %{remote_ip}:%{remote_port}\n' \
        --resolve "${IQM_HOST}:${LOCAL_PORT}:127.0.0.1" \
        "https://${IQM_HOST}:${LOCAL_PORT}/"
    exit $?
fi

echo "Tunnel: ${BIND_ADDR}:${LOCAL_PORT} -> ${HUB} -> ${IQM_HOST}:${IQM_PORT}"
echo "Point the cluster at: QFW_QC_URL=https://${IQM_HOST}:${LOCAL_PORT}"
echo "(Ctrl-C to stop.)"

run_tunnel() {
    # -N: no remote command, forwarding only.
    # ExitOnForwardFailure: fail loudly if the local port is taken or hub
    #   refuses forwarding, instead of sitting there looking connected.
    # ServerAlive*: notice a dead tunnel within ~90s rather than hanging a job.
    ssh -N \
        -o ExitOnForwardFailure=yes \
        -o ServerAliveInterval=30 \
        -o ServerAliveCountMax=3 \
        -L "${BIND_ADDR}:${LOCAL_PORT}:${IQM_HOST}:${IQM_PORT}" \
        "${HUB}"
}

if ${ONCE}; then
    run_tunnel
    exit $?
fi

trap 'echo; echo "Tunnel stopped."; exit 0' INT TERM

while true; do
    run_tunnel
    status=$?
    echo "ssh exited (status ${status}); reconnecting in ${RETRY_DELAY}s..." >&2
    sleep "${RETRY_DELAY}"
done
