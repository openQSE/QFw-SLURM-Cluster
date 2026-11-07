#!/usr/bin/env bash
#
# Install the COMPSs runtime and its Python binding into the cluster image.
#
# Used by the Dockerfile when QFW_WITH_COMPSS=1, and by Dockerfile.compss to
# layer COMPSs onto an already-built or pulled cluster image.
#
# The binding is compiled against the image's system Python, which is the same
# 3.12 interpreter the QFw venv and defw-python are built on. That shared
# version is what lets a COMPSs task run under the QFw venv and launch
# defw-python without a version mismatch.
#
# Only the parts a Slurm deployment uses are kept: the runtime, the Python
# binding and the queue-system scripts. The C binding, the Kafka streaming
# backend and the monitor are left out. So is tracing (Extrae), unless
# COMPSS_WITH_TRACING=1.

set -euo pipefail

COMPSS_VERSION="${COMPSS_VERSION:-3.4}"
COMPSS_URL="${COMPSS_URL:-https://compss.bsc.es/repo/sc/stable/COMPSs_${COMPSS_VERSION}.tar.gz}"
COMPSS_HOME="${COMPSS_HOME:-/opt/COMPSs}"
COMPSS_SC_CFG="${COMPSS_SC_CFG:-}"
COMPSS_WITH_TRACING="${COMPSS_WITH_TRACING:-0}"

# lsof and netstat are what launch_compss uses to find a free master port.
dnf -y install java-21-openjdk-devel lsof net-tools
if [[ ${COMPSS_WITH_TRACING} == 1 ]]; then
	dnf -y install autoconf automake libtool make gcc gcc-c++ gcc-gfortran \
		libxml2-devel
fi
dnf clean all
rm -rf /var/cache/yum /var/cache/dnf

JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
export JAVA_HOME
test -f "${JAVA_HOME}/include/jni.h"

# The binding installs with pip --no-build-isolation, so its build
# requirements must already be in the interpreter that runs install.sh.
uv pip install --system setuptools wheel cython dill

work_dir="$(mktemp -d)"
trap 'rm -rf "${work_dir}"' EXIT

curl -fsSL "${COMPSS_URL}" | tar -xz -C "${work_dir}"

# The installer is a copy-then-build script. Removing the unused payload
# before it runs keeps it out of the image layer entirely.
rm -rf "${work_dir}/COMPSs/Dependencies/kafka" \
	"${work_dir}/COMPSs/Tools/monitor"

(cd "${work_dir}/COMPSs" && ./install --no-tracing --no-c-binding "${COMPSS_HOME}")

rm -rf "${COMPSS_HOME}/Dependencies/extrae" \
	"${COMPSS_HOME}/Dependencies/kafka" \
	"${COMPSS_HOME}/Tools/monitor"

if [[ ${COMPSS_WITH_TRACING} == 1 ]]; then
	# GCC 14 rejects some older C in Extrae; -fpermissive makes those warnings
	# again. The plain PATH keeps QFw's MPI out of the build: trace merging
	# does not need it.
	(cd "${work_dir}/COMPSs/Dependencies" &&
		PATH=/usr/bin:/bin:/usr/sbin:/sbin CFLAGS="-O2 -g -fpermissive" \
		./install_extrae.sh "${work_dir}/COMPSs/Dependencies/extrae" \
			"${COMPSS_HOME}/Dependencies/extrae" false)
	test -x "${COMPSS_HOME}/Dependencies/extrae/bin/mpi2prv"
fi

if [[ -n "${COMPSS_SC_CFG}" ]]; then
	install -m 0644 "${COMPSS_SC_CFG}" \
		"${COMPSS_HOME}/Runtime/scripts/queues/supercomputers/qfw-cluster.cfg"
fi

cat > /etc/profile.d/compss.sh <<EOF
export COMPSS_HOME=${COMPSS_HOME}
export JAVA_HOME=${JAVA_HOME}
case ":\${PATH}:" in
	*":${COMPSS_HOME}/Runtime/scripts/user:"*) ;;
	*) export PATH="${COMPSS_HOME}/Runtime/scripts/user:\${PATH}" ;;
esac
EOF
chmod 0644 /etc/profile.d/compss.sh

"${COMPSS_HOME}/Runtime/scripts/user/runcompss" --version
# The compss extension links libjvm and bindings-common at runtime, which
# runcompss puts on LD_LIBRARY_PATH. Importing the package is enough here.
PYTHONPATH="${COMPSS_HOME}/Bindings/python/3" python3 -c \
	'import pycompss; print("pycompss", pycompss.__file__)'
ls "${COMPSS_HOME}"/Bindings/python/3/compss*.so
