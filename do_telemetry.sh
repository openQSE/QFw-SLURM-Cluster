#!/bin/bash
#
# Start, stop or inspect the optional telemetry stack beside the running
# cluster: the OpenTelemetry Collector, Prometheus, Tempo, Loki and Grafana from
# docker-compose.telemetry.yml. The cluster's own containers are never
# recreated by this script.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"
SERVICES=(otel-collector prometheus tempo loki grafana)

usage() {
    cat <<USAGE
Usage: $(basename "$0") ACTION [compose arguments]

Actions:
  up        Start the telemetry stack (pulls the pinned images on first use)
  down      Stop and remove its containers, keeping the data volumes
  purge     down, then remove the Prometheus, Tempo, Loki and Grafana volumes
  status    Show its containers
  logs      Follow its logs (extra arguments go to docker compose logs)
  url       Print where Grafana is

The cluster containers only pick up the QFw telemetry variables when they
are created. Either configure the overlay in with ./do_configure.sh
--telemetry before ./do_startup.sh, or run ./do_restart.sh --force-recreate
once the overlay is in COMPOSE_FILE. See docker-compose.telemetry.yml.
USAGE
}

if [ ! -f "${ENV_FILE}" ]; then
    echo "Missing ${ENV_FILE}. Run ./do_configure.sh first." >&2
    exit 1
fi

# The same files the cluster runs with, plus the overlay. Compose only
# includes docker-compose.override.yml on its own when no -f is given, so
# it is named here when present; otherwise compose would see a different
# configuration for the cluster's services.
FILES=(-f "${SCRIPT_DIR}/docker-compose.yml")
if [ -f "${SCRIPT_DIR}/docker-compose.override.yml" ]; then
    FILES+=(-f "${SCRIPT_DIR}/docker-compose.override.yml")
fi
FILES+=(-f "${SCRIPT_DIR}/docker-compose.telemetry.yml")
COMPOSE=(docker compose --env-file "${ENV_FILE}" --project-directory "${SCRIPT_DIR}" "${FILES[@]}")

grafana_port() {
    local port="${QFW_GRAFANA_PORT:-}"
    if [ -z "${port}" ]; then
        port="$(awk -F= '$1 == "QFW_GRAFANA_PORT" { print $2 }' "${ENV_FILE}" | tail -n 1)"
    fi
    echo "${port:-3000}"
}

project_name() {
    "${COMPOSE[@]}" config --format json 2>/dev/null \
        | python3 -c 'import json, sys; print(json.load(sys.stdin)["name"])'
}

action="${1:-}"
shift || true
case "${action}" in
    up)
        "${COMPOSE[@]}" up -d --no-recreate "${SERVICES[@]}" "$@"
        echo "Grafana: http://localhost:$(grafana_port)/ (anonymous viewers; admin password in QFW_GRAFANA_ADMIN_PASSWORD, default qfw-demo)"
        echo "Prometheus: http://localhost:9090/  Tempo: http://localhost:3200/  Loki: http://localhost:3100/  OTLP/HTTP: http://localhost:4318/"
        ;;
    down)
        "${COMPOSE[@]}" rm --stop --force "${SERVICES[@]}" "$@"
        ;;
    purge)
        "${COMPOSE[@]}" rm --stop --force "${SERVICES[@]}"
        project="$(project_name)"
        if [ -z "${project}" ]; then
            echo "Could not determine the compose project name; volumes not removed." >&2
            exit 1
        fi
        docker volume rm "${project}_prometheus_data" "${project}_tempo_data" "${project}_loki_data" "${project}_grafana_data"
        ;;
    status)
        "${COMPOSE[@]}" ps "${SERVICES[@]}" "$@"
        ;;
    logs)
        "${COMPOSE[@]}" logs --follow --tail=100 "${SERVICES[@]}" "$@"
        ;;
    url)
        echo "http://localhost:$(grafana_port)/"
        ;;
    -h|--help|help|"")
        usage
        [ -n "${action}" ] || exit 1
        ;;
    *)
        echo "Unknown action: ${action}" >&2
        usage >&2
        exit 1
        ;;
esac
