#!/bin/bash
#
# Fetch the telemetry stack's release binaries for a bare-metal install: the
# OpenTelemetry Collector (contrib), Prometheus, Tempo, Loki and Grafana, at
# the versions the container stack runs (docker-compose.telemetry.yml), with
# their published checksums verified.
#
# Run it wherever the internet is reachable. On a host behind a proxy, set
# https_proxy (curl honours it); on a host with no route out at all, run it
# elsewhere and carry the dist directory in.
#
#   telemetry/baremetal/fetch.sh [--arch amd64|arm64] [--dest DIR]
#
# Defaults: the architecture of the machine running the script, and
# ./telemetry-dist. Already-verified files are kept, so a rerun only fetches
# what is missing.
set -euo pipefail

OTELCOL_VERSION=0.162.0
PROMETHEUS_VERSION=3.15.0
TEMPO_VERSION=3.1.0
LOKI_VERSION=3.7.8
GRAFANA_VERSION=13.2.3

ARCH=""
DEST="telemetry-dist"
while [[ $# -gt 0 ]]; do
	case "$1" in
		--arch) ARCH="$2"; shift 2 ;;
		--dest) DEST="$2"; shift 2 ;;
		-h|--help) sed -n '2,19p' "$0"; exit 0 ;;
		*) echo "fetch.sh: unknown option $1" >&2; exit 2 ;;
	esac
done
if [[ -z "${ARCH}" ]]; then
	case "$(uname -m)" in
		x86_64|amd64) ARCH=amd64 ;;
		aarch64|arm64) ARCH=arm64 ;;
		*) echo "fetch.sh: pass --arch amd64 or arm64 (host is $(uname -m))" >&2; exit 2 ;;
	esac
fi
mkdir -p "${DEST}"
DEST="$(cd "${DEST}" && pwd)"

sha256_of() {
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$1" | awk '{print $1}'
	else
		shasum -a 256 "$1" | awk '{print $1}'
	fi
}

# fetch NAME URL CHECKSUM_URL
#   CHECKSUM_URL is either a sums file ("<sha>  <file>" lines) or a file
#   holding one checksum; both are read by matching the file name first and
#   falling back to the first field.
fetch() {
	local name="$1" url="$2" sums="$3" expected
	expected="$(curl -fsSL --retry 3 "${sums}" | awk -v f="${name}" '
		$2 == f || $2 == "*" f { print $1; exit }
		NF == 1 && NR == 1 { print $1; exit }')"
	if [[ -z "${expected}" ]]; then
		echo "fetch.sh: no checksum for ${name} in ${sums}" >&2
		exit 1
	fi
	if [[ -f "${DEST}/${name}" ]] && [[ "$(sha256_of "${DEST}/${name}")" == "${expected}" ]]; then
		echo "  kept    ${name}"
		return
	fi
	echo "  fetch   ${name}"
	curl -fL --retry 3 --progress-bar -o "${DEST}/${name}.part" "${url}"
	local actual
	actual="$(sha256_of "${DEST}/${name}.part")"
	if [[ "${actual}" != "${expected}" ]]; then
		rm -f "${DEST}/${name}.part"
		echo "fetch.sh: checksum mismatch for ${name}: ${actual} != ${expected}" >&2
		exit 1
	fi
	mv "${DEST}/${name}.part" "${DEST}/${name}"
	echo "  ok      ${name}"
}

echo "telemetry stack for linux/${ARCH} into ${DEST}"
otel="otelcol-contrib_${OTELCOL_VERSION}_linux_${ARCH}.tar.gz"
fetch "${otel}" \
	"https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v${OTELCOL_VERSION}/${otel}" \
	"https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v${OTELCOL_VERSION}/${otel}.sha256"
prom="prometheus-${PROMETHEUS_VERSION}.linux-${ARCH}.tar.gz"
fetch "${prom}" \
	"https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/${prom}" \
	"https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/sha256sums.txt"
tempo="tempo_${TEMPO_VERSION}_linux_${ARCH}.tar.gz"
fetch "${tempo}" \
	"https://github.com/grafana/tempo/releases/download/v${TEMPO_VERSION}/${tempo}" \
	"https://github.com/grafana/tempo/releases/download/v${TEMPO_VERSION}/SHA256SUMS"
loki="loki-linux-${ARCH}.zip"
fetch "${loki}" \
	"https://github.com/grafana/loki/releases/download/v${LOKI_VERSION}/${loki}" \
	"https://github.com/grafana/loki/releases/download/v${LOKI_VERSION}/SHA256SUMS"
grafana="grafana-${GRAFANA_VERSION}.linux-${ARCH}.tar.gz"
fetch "${grafana}" \
	"https://dl.grafana.com/oss/release/${grafana}" \
	"https://dl.grafana.com/oss/release/${grafana}.sha256"

cat > "${DEST}/MANIFEST" <<EOF
arch=${ARCH}
otelcol=${otel}
prometheus=${prom}
tempo=${tempo}
loki=${loki}
grafana=${grafana}
otelcol_version=${OTELCOL_VERSION}
prometheus_version=${PROMETHEUS_VERSION}
tempo_version=${TEMPO_VERSION}
loki_version=${LOKI_VERSION}
grafana_version=${GRAFANA_VERSION}
EOF
echo "done: $(du -sh "${DEST}" | cut -f1) in ${DEST} (MANIFEST written)"
