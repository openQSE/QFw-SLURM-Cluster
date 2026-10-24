# Source this file from the top-level do_*.sh helpers, after ENV_FILE is set.
#
# Export COMPOSE_FILE from qfw-install.env so the helper scripts, and any
# docker compose call they make, use the overlay list chosen with
# ./do_configure.sh (--telemetry, --qsa-sim). A COMPOSE_FILE already set in the
# caller's environment takes precedence.

if [ -z "${COMPOSE_FILE:-}" ] && [ -f "${ENV_FILE:-}" ]; then
    COMPOSE_FILE="$(awk -F= '$1 == "COMPOSE_FILE" {
        print substr($0, index($0, "=") + 1)
    }' "${ENV_FILE}" | tail -n 1)"
    if [ -n "${COMPOSE_FILE}" ]; then
        export COMPOSE_FILE
    else
        unset COMPOSE_FILE
    fi
fi
