FROM rockylinux/rockylinux:10.1.20251123

LABEL org.opencontainers.image.source="https://github.com/giovtorres/slurm-docker-cluster" \
      org.opencontainers.image.title="slurm-docker-cluster" \
      org.opencontainers.image.description="Slurm Docker cluster on Rocky Linux 10.1" \
      org.label-schema.docker.cmd="docker compose up -d" \
      maintainer="Giovanni Torres"

#      org.label-schema.docker.cmd="docker-compose up -d" \

####
# XXX: Getting curl certificate errors with rockylinux
#      when try to get the mirror list during 'yum makecache'
#      My HACK is to just disable SSL cert validation in a very
#      heavy handed way.
####
RUN set -ex \
  && echo 'sslverify=false' >> /etc/yum.conf \
    && dnf makecache \
    && dnf -y update \
    && dnf -y install dnf-plugins-core \
    && dnf -y install epel-release \
    && dnf config-manager --set-enabled crb \
    && dnf -y install \
       autoconf \
       automake \
       bison \
       bzip2-devel \
       diffutils \
       expat-devel \
       file \
       flex \
       wget \
       bzip2 \
       curl \
       findutils \
       gdbm-devel \
       gzip \
       libffi-devel \
       libcurl-devel \
       libtool \
       lua \
       lua-devel \
       m4 \
       ncurses-devel \
       openssl \
       openssl-devel \
       openssh-clients \
       openssh-server \
       perl \
       patch \
       libuuid-devel \
       readline-devel \
       sqlite-devel \
       tar \
       tk-devel \
       gcc \
       gcc-c++ \
       gcc-gfortran \
       git \
       gnupg \
       make \
       munge \
       munge-devel \
       python3.12-devel \
       python3-devel \
       python3-pip \
       python3 \
       mariadb-server \
       mariadb-devel \
       psmisc \
       bash-completion \
       xz-devel \
       vim-enhanced \
       json-c-devel \
       libjwt-devel \
       libyaml-devel \
       zlib-devel \
    && dnf clean all \
    && rm -rf /var/cache/yum

RUN pip3 install Cython pytest

ARG HTTP_PARSER_VERSION=v2.9.4
ARG HTTP_PARSER_PREFIX=/opt/qfw/http-parser

RUN set -ex \
    && git clone --branch "${HTTP_PARSER_VERSION}" --depth=1 https://github.com/nodejs/http-parser.git /tmp/http-parser \
    && cd /tmp/http-parser \
    && make -j"$(nproc)" package library \
    && mkdir -p "${HTTP_PARSER_PREFIX}/include" "${HTTP_PARSER_PREFIX}/lib" \
    && cp http_parser.h "${HTTP_PARSER_PREFIX}/include/" \
    && cp libhttp_parser.a "${HTTP_PARSER_PREFIX}/lib/" \
    && cp libhttp_parser.so* "${HTTP_PARSER_PREFIX}/lib/" \
    && rm -rf /tmp/http-parser

ARG GOSU_VERSION=1.17
ARG TARGETARCH

#    && gpg --batch --keyserver hkps://keys.openpgp.org --recv-keys B42F6819007F00F88E364FD4036A9C25BF357DD4 \

RUN set -ex \
    && wget -O /usr/local/bin/gosu "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-${TARGETARCH}" \
    && wget -O /usr/local/bin/gosu.asc "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-${TARGETARCH}.asc" \
    && export GNUPGHOME="$(mktemp -d)" \
    && curl --insecure -fsSL "https://keys.openpgp.org/pks/lookup?op=get&search=0xB42F6819007F00F88E364FD4036A9C25BF357DD4" | gpg --import \
    && gpg --batch --verify /usr/local/bin/gosu.asc /usr/local/bin/gosu \
    && rm -rf "${GNUPGHOME}" /usr/local/bin/gosu.asc \
    && chmod +x /usr/local/bin/gosu \
    && gosu nobody true

ARG SLURM_TAG
ARG GCC13_ROOT=/usr
ARG LIBFABRIC_REF=v2.3.1
ARG LIBFABRIC_PREFIX=/opt/qfw/libfabric
ARG OMPI_REF=v5.0.9
ARG OMPI_PREFIX=/opt/qfw/openmpi
ARG OSU_OMB_VERSION=7.5.2
ARG OSU_OMB_PREFIX=/opt/qfw/osu-micro-benchmarks

RUN set -x \
    && git clone -b ${SLURM_TAG} --single-branch --depth=1 https://github.com/SchedMD/slurm.git \
    && pushd slurm \
    && ./configure --enable-debug --prefix=/usr --sysconfdir=/etc/slurm \
        --with-mysql_config=/usr/bin  --libdir=/usr/lib64 \
        --with-http-parser="${HTTP_PARSER_PREFIX}" --with-yaml=/usr --with-jwt=/usr \
    && make install \
    && test -x /usr/lib64/slurm/job_submit_lua.so \
    && test -x /usr/lib64/slurm/burst_buffer_lua.so \
    && install -D -m644 etc/cgroup.conf.example /etc/slurm/cgroup.conf.example \
    && install -D -m644 etc/slurm.conf.example /etc/slurm/slurm.conf.example \
    && install -D -m644 etc/slurmdbd.conf.example /etc/slurm/slurmdbd.conf.example \
    && install -D -m644 contribs/slurm_completion_help/slurm_completion.sh /etc/profile.d/slurm_completion.sh \
    && sed -i '1a case $- in *i*) ;; *) return 0 2>/dev/null || exit 0 ;; esac' \
        /etc/profile.d/slurm_completion.sh \
    && popd \
    && rm -rf slurm \
    && groupadd -r --gid=990 slurm \
    && useradd -r -g slurm --uid=990 slurm \
    && mkdir /etc/sysconfig/slurm \
        /var/spool/slurmd \
        /var/run/slurmd \
        /var/run/slurmdbd \
        /var/lib/slurmd \
        /var/log/slurm \
        /data \
    && touch /var/lib/slurmd/node_state \
        /var/lib/slurmd/front_end_state \
        /var/lib/slurmd/job_state \
        /var/lib/slurmd/resv_state \
        /var/lib/slurmd/trigger_state \
        /var/lib/slurmd/assoc_mgr_state \
        /var/lib/slurmd/assoc_usage \
        /var/lib/slurmd/qos_usage \
        /var/lib/slurmd/fed_mgr_state \
    && chown -R slurm:slurm /var/*/slurm* \
    && install -d -m 0700 /etc/munge \
    && dd if=/dev/urandom bs=1 count=1024 of=/etc/munge/munge.key status=none \
    && chown -R munge:munge /etc/munge \
    && chmod 0400 /etc/munge/munge.key

RUN set -ex \
    && dnf -y install environment-modules \
    && dnf clean all \
    && rm -rf /var/cache/yum

RUN set -ex \
    && export PATH="${GCC13_ROOT}/bin:${PATH}" \
    && export LD_LIBRARY_PATH="${GCC13_ROOT}/lib64:${LD_LIBRARY_PATH}" \
    && export CC="${GCC13_ROOT}/bin/gcc" \
    && export CXX="${GCC13_ROOT}/bin/g++" \
    && export FC="${GCC13_ROOT}/bin/gfortran" \
    && git clone https://github.com/ofiwg/libfabric.git /tmp/libfabric \
    && cd /tmp/libfabric \
    && git checkout "${LIBFABRIC_REF}" \
    && ./autogen.sh \
    && ./configure --prefix="${LIBFABRIC_PREFIX}" CC="${CC}" CXX="${CXX}" FC="${FC}" \
    && make -j"$(nproc)" all \
    && make install \
    && rm -rf /tmp/libfabric

RUN set -ex \
    && export PATH="${GCC13_ROOT}/bin:${PATH}" \
    && export LD_LIBRARY_PATH="${GCC13_ROOT}/lib64:${LD_LIBRARY_PATH}" \
    && export CC="${GCC13_ROOT}/bin/gcc" \
    && export CXX="${GCC13_ROOT}/bin/g++" \
    && export FC="${GCC13_ROOT}/bin/gfortran" \
    && export PKG_CONFIG_PATH="${LIBFABRIC_PREFIX}/lib/pkgconfig:${PKG_CONFIG_PATH}" \
    && export CPPFLAGS="-I${LIBFABRIC_PREFIX}/include ${CPPFLAGS}" \
    && export LDFLAGS="-L${LIBFABRIC_PREFIX}/lib ${LDFLAGS}" \
    && git clone --recursive --branch "${OMPI_REF}" https://github.com/open-mpi/ompi.git /tmp/ompi \
    && cd /tmp/ompi \
    && ./autogen.pl \
    && ./configure --prefix="${OMPI_PREFIX}" --with-libfabric="${LIBFABRIC_PREFIX}" --with-slurm CC="${CC}" CXX="${CXX}" FC="${FC}" \
    && make -j"$(nproc)" all \
    && make install \
    && rm -rf /tmp/ompi

RUN set -ex \
    && export PATH="${OMPI_PREFIX}/bin:${PATH}" \
    && export LD_LIBRARY_PATH="${OMPI_PREFIX}/lib:${LIBFABRIC_PREFIX}/lib:${LD_LIBRARY_PATH}" \
    && cd /tmp \
    && curl -L -o osu-micro-benchmarks-${OSU_OMB_VERSION}.tar.gz \
        https://mvapich.cse.ohio-state.edu/download/mvapich/osu-micro-benchmarks-${OSU_OMB_VERSION}.tar.gz \
    && tar --no-same-owner -xzf osu-micro-benchmarks-${OSU_OMB_VERSION}.tar.gz \
    && cd osu-micro-benchmarks-${OSU_OMB_VERSION} \
    && ./configure CC=mpicc CXX=mpicxx --prefix="${OSU_OMB_PREFIX}" \
    && make -j"$(nproc)" all \
    && make install \
    && rm -rf /tmp/osu-micro-benchmarks-${OSU_OMB_VERSION} /tmp/osu-micro-benchmarks-${OSU_OMB_VERSION}.tar.gz

RUN set -ex \
    && yum -y install \
       cmake \
       gcc-gfortran \
       openblas-devel \
       swig \
    && yum clean all \
    && rm -rf /var/cache/yum

ARG QFW_BUILD_JOBS=4

# The image contains a complete release installation. A checkout mounted under
# QFW_BASE remains an optional developer override built by do_qfw_build.sh.
ARG QFW_REPOSITORY=https://github.com/openQSE/QFw.git
ARG QFW_REF=main
ARG QFW_DEFW_REPOSITORY=
ARG QFW_SLURM_REPOSITORY=https://github.com/openQSE/qfw-slurm.git
ARG QFW_SLURM_REF=main
ARG QFW_IMAGE_SOURCE=/tmp/qfw-source
ARG QFW_IMAGE_BUILD=/tmp/qfw-build
ARG QFW_IMAGE_PREFIX=/opt/openqse/qfw
ARG QFW_IMAGE_VENV=/opt/openqse/qfw-venv
ARG QFW_SLURM_SOURCE=/tmp/qfw-slurm-source
ARG QFW_SLURM_BUILD=/tmp/qfw-slurm-build
ARG QFW_SLURM_PREFIX=/opt/openqse/qfw-slurm
ARG NWQSIM_PREFIX=/opt/openqse/nwqsim
ARG TNQVM_PREFIX=/opt/openqse/tnqvm
ARG SIMULATOR_WORK_ROOT=/tmp/qfw-simulator-build

ENV QFW_BASE=/workspace/qfw-container-base \
    QFW_BUILD_JOBS=${QFW_BUILD_JOBS}

ENV PATH=${OMPI_PREFIX}/bin:${LIBFABRIC_PREFIX}/bin:${PATH}

ENV LD_LIBRARY_PATH=${OMPI_PREFIX}/lib:${LIBFABRIC_PREFIX}/lib

# ----------------------------------------------------------------------
# QRMI / QDMI shim dependencies
#
# Lower-level interface libraries the QFw front-end shim will route to.
# ----------------------------------------------------------------------

ARG RUST_VERSION=1.91.0
ENV CARGO_HOME=/opt/qfw/rust/cargo \
    RUSTUP_HOME=/opt/qfw/rust/rustup
RUN set -ex \
    && mkdir -p "${CARGO_HOME}" "${RUSTUP_HOME}" \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --no-modify-path --profile minimal \
            --default-toolchain "${RUST_VERSION}" \
    && chmod -R a+rwX /opt/qfw/rust
ENV PATH=${CARGO_HOME}/bin:${PATH}

RUN set -ex \
    && dnf -y install ninja-build \
    && dnf clean all \
    && rm -rf /var/cache/yum

# QRMI: build the C library (libqrmi.so + qrmi.h) and the SLURM SPANK plugin
# from source, then install the matching Python bindings from PyPI.
#
# A single QRMI_VERSION drives both the git tag (for the C library and the
# SPANK plugin's QRMI_ROOT) and the PyPI release (for the Python bindings),
# so the C ABI loaded by C/C++ shim consumers matches the bindings loaded
# into the QFw venv.
#
# NOTE: upstream changed tag convention around the 0.14 release from
# "vX.Y.Z" to "X.Y.Z" (no leading v). Use the unprefixed form for any
# release >= 0.14.0; older releases need the "v" prefix.
# QRMI 0.24.4 with spank-plugins 0.11.0. The plugin links the locally-cloned
# QRMI via -DQRMI_ROOT, so it must be built against whatever QRMI_VERSION says.
# Bumping either ARG invalidates the whole RUN layer below, which rebuilds the
# plugin from scratch, as QRMI's release announcement asks for.
#
# 0.24.4 brings the default QuantumResource trait implementations (upstream
# issue #236, which cites the openQSE QRMI/QDMI analysis report as motivation).
# A vendor now only overrides what its backend supports and the rest return
# UnsupportedFunction. For IQM, acquire() still returns a generated UUID without
# contacting the provider, but it now also logs
#   WARN qrmi: acquiring resource is not implemented by this resource(...)
# That warning arrives with no RUST_LOG set, because the Rust-to-Python log
# bridge is level-filtered rather than off by default. WARN passes, DEBUG does
# not. So the silent no-op is now an announced one.
#
# THE HEALTH-STATUS GAP IS STILL OPEN AND STILL DOES NOT AFFECT US. 0.24.3 was
# announced as fixing is_accessible() against old IQM servers. It fixes one
# meaning of old, a server that nests health but omits operational, which now
# defaults to "online". It does NOT fix a server whose response is genuinely
# flat, because the health field itself is still required with no default and
# no alias. THE ORNL q20 IS STILL FLAT, verified 2026-09-08:
#   {"healthy": true, "updated_at": "..."}
# so is_accessible() still raises there. The error moved rather than went away,
# from missing field `operational` on 0.24.0 to missing field `health` on
# 0.24.4. Reported upstream.
#
# QFw is unaffected because it never calls is_accessible(). That call is absent
# from QrmiDriver.CAPABILITIES and from services/ entirely. target() was
# re-verified against the q20 on 0.24.4 and returns 20 qubits normally.
#
# IF is_accessible() IS EVER WIRED INTO THE SHIM, this pin becomes a live
# problem until either ORNL's IQM API or QRMI's health model is updated. That
# is the trigger to revisit.
#
# 0.24.0 also added typed errors. The new Python exceptions all subclass
# RuntimeError, which is what the drivers already catch, so that half is purely
# additive.
#
# Earlier context worth keeping: 0.23.0 renamed the IBM Qiskit Runtime Service
# resource type to IBM Quantum Compute Service (QRMI_IBM_QRS_ -> QRMI_IBM_QCS_,
# legacy accepted until 2026-11-21), and 0.22.0 added the static architecture to
# target() plus Rust-to-Python log bridging and a GIL deadlock fix. The renames
# do not reach QFw, which opens ResourceType.IQMServer and reads
# {backend}_QRMI_IQM_ISA_*. The static architecture does: it arrives as a list,
# and services/svc_lib_qpm/drivers/qrmi_driver.py unwraps it before handing it
# to qhw-iqm.
ARG QRMI_REPO=https://github.com/qiskit-community/qrmi.git
ARG QRMI_VERSION=0.24.4
ARG QRMI_PREFIX=/opt/qfw/qrmi
ARG QRMI_SPANK_REPO=https://github.com/qiskit-community/spank-plugins.git
ARG QRMI_SPANK_REF=0.11.0
RUN set -ex \
    && git clone --depth=1 --branch "${QRMI_VERSION}" "${QRMI_REPO}" /tmp/qrmi \
    && cd /tmp/qrmi \
    && cargo build --locked --release --lib \
    && mkdir -p "${QRMI_PREFIX}/lib" "${QRMI_PREFIX}/include" \
    && cp target/release/libqrmi.so "${QRMI_PREFIX}/lib/" \
    && (cp target/release/libqrmi.a "${QRMI_PREFIX}/lib/" 2>/dev/null || true) \
    && cp qrmi.h "${QRMI_PREFIX}/include/" \
    && git clone --depth=1 --branch "${QRMI_SPANK_REF}" \
        "${QRMI_SPANK_REPO}" /tmp/spank-plugins \
    && cd /tmp/spank-plugins/plugins/spank_qrmi \
    && cmake -S . -B build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DQRMI_ROOT=/tmp/qrmi \
    && cmake --build build \
    && install -d /usr/lib64/slurm \
    && find build -maxdepth 3 -name '*.so' -exec \
        install -m 0755 {} /usr/lib64/slurm/ \; \
    && rm -rf /tmp/qrmi /tmp/spank-plugins

# Obtain QFw solely as the versioned source for the independent simulator
# builders and the official QFw installation. QFw's CMake install does not
# invoke either simulator builder.
ARG QFW_SOURCE_REVISION
RUN set -ex \
    && git -c url.https://github.com/.insteadOf=git@github.com: \
        clone "${QFW_REPOSITORY}" "${QFW_IMAGE_SOURCE}" \
    && git -C "${QFW_IMAGE_SOURCE}" fetch origin "${QFW_REF}" \
    && git -C "${QFW_IMAGE_SOURCE}" switch --detach FETCH_HEAD \
    && test "$(git -C "${QFW_IMAGE_SOURCE}" rev-parse HEAD)" = \
        "${QFW_SOURCE_REVISION}" \
    && if [ -n "${QFW_DEFW_REPOSITORY}" ]; then \
        git -C "${QFW_IMAGE_SOURCE}" config submodule.DEFw.url \
            "${QFW_DEFW_REPOSITORY}"; \
       fi \
    && git -C "${QFW_IMAGE_SOURCE}" \
        -c url.https://github.com/.insteadOf=git@github.com: \
        submodule update --init --recursive

RUN set -ex \
    && "${QFW_IMAGE_SOURCE}/tools/dependencies/nwqsim/build.sh" \
        --work-dir "${SIMULATOR_WORK_ROOT}/nwqsim" \
        --prefix "${NWQSIM_PREFIX}" \
        --jobs "${QFW_BUILD_JOBS}" \
        --rocm off \
    && test -x "${NWQSIM_PREFIX}/bin/circuit_runner.nwqsim"

RUN set -ex \
    && "${QFW_IMAGE_SOURCE}/tools/dependencies/tnqvm/build.sh" \
        --work-dir "${SIMULATOR_WORK_ROOT}/tnqvm" \
        --prefix "${TNQVM_PREFIX}" \
        --mpi-prefix "${OMPI_PREFIX}" \
        --jobs "${QFW_BUILD_JOBS}" \
        --rocm off \
    && test -x "${TNQVM_PREFIX}/bin/circuit_runner.tnqvm" \
    && test -f "${TNQVM_PREFIX}/xacc/plugins/libtnqvm.so"

# The shim's QRMI/QDMI dependencies. Keep these in step with do_qfw_build.sh,
# which installs the same packages for the developer build. The two lists
# drifted once already, and the image kept building without error while its
# QDMI leg could not import.
#
# mqt-core 3.9.2: services/svc_lib_qpm/drivers/qdmi_driver.py imports
# mqt.core.qdmi.driver, which does not exist before 3.9.
#
# iqm-qdmi>=1.4 without the [qiskit] extra, as do_qfw_build.sh does. The shim
# never imports iqm.qdmi.qiskit, and Qiskit already comes from
# setup/requirements.txt. Combined with an older mqt-core pin, that extra is
# also what let pip settle on iqm-qdmi 1.2.0.
RUN set -ex \
    && python3 -m venv "${QFW_IMAGE_VENV}" \
    && "${QFW_IMAGE_VENV}/bin/python" -m pip install --upgrade \
        pip setuptools wheel \
    && "${QFW_IMAGE_VENV}/bin/python" -m pip install \
        -r "${QFW_IMAGE_SOURCE}/setup/build-requirements.txt" \
        -r "${QFW_IMAGE_SOURCE}/setup/requirements.txt" \
        "qrmi==${QRMI_VERSION}" \
        'iqm-qdmi>=1.4' \
        'mqt-core==3.9.2' \
        'jsonschema>=4' \
    && PATH="${QFW_IMAGE_VENV}/bin:${PATH}" cmake \
        -S "${QFW_IMAGE_SOURCE}" \
        -B "${QFW_IMAGE_BUILD}" \
        -DCMAKE_BUILD_TYPE=RelWithDebInfo \
        -DCMAKE_INSTALL_PREFIX="${QFW_IMAGE_PREFIX}" \
        -DQFW_BUILD_BUNDLED_DEFW=ON \
    && cmake --build "${QFW_IMAGE_BUILD}" \
        --parallel "${QFW_BUILD_JOBS}" \
    && cmake --install "${QFW_IMAGE_BUILD}" \
    && test -x "${QFW_IMAGE_PREFIX}/bin/qfw-activate" \
    && rm -rf "${QFW_IMAGE_SOURCE}" "${QFW_IMAGE_BUILD}" \
        "${SIMULATOR_WORK_ROOT}"

ARG QFW_SLURM_SOURCE_REVISION
RUN set -ex \
    && git clone "${QFW_SLURM_REPOSITORY}" "${QFW_SLURM_SOURCE}" \
    && git -C "${QFW_SLURM_SOURCE}" fetch origin "${QFW_SLURM_REF}" \
    && git -C "${QFW_SLURM_SOURCE}" switch --detach FETCH_HEAD \
    && test "$(git -C "${QFW_SLURM_SOURCE}" rev-parse HEAD)" = \
        "${QFW_SLURM_SOURCE_REVISION}" \
    && "${QFW_IMAGE_VENV}/bin/python" -m pip install \
        --no-build-isolation "${QFW_SLURM_SOURCE}" pytest \
    && cmake -S "${QFW_SLURM_SOURCE}" -B "${QFW_SLURM_BUILD}" \
        -DCMAKE_BUILD_TYPE=RelWithDebInfo \
        -DCMAKE_INSTALL_PREFIX="${QFW_SLURM_PREFIX}" \
        -DPython3_EXECUTABLE="${QFW_IMAGE_VENV}/bin/python" \
    && cmake --build "${QFW_SLURM_BUILD}" \
        --parallel "${QFW_BUILD_JOBS}" \
    && install -d -o munge -g munge -m 0700 /etc/munge /var/log/munge \
    && install -d -o munge -g munge -m 0755 /run/munge \
    && dd if=/dev/urandom of=/etc/munge/munge.key bs=1024 count=1 \
        status=none \
    && chown munge:munge /etc/munge/munge.key \
    && chmod 0400 /etc/munge/munge.key \
    && gosu munge /usr/sbin/munged \
    && ctest --test-dir "${QFW_SLURM_BUILD}" --output-on-failure \
    && pkill -u munge munged \
    && rm -f /etc/munge/munge.key /run/munge/munge.pid \
        /run/munge/munge.socket.2 \
    && cmake --install "${QFW_SLURM_BUILD}" \
    && install -d -m 0755 /usr/local/share/man \
    && cp -a "${QFW_SLURM_PREFIX}/share/man/." /usr/local/share/man/ \
    && install -o root -g root -m 0755 \
        "${QFW_SLURM_PREFIX}/lib64/slurm/spank_quantum.so" \
        /usr/lib64/slurm/spank_quantum.so \
    && test -x "${QFW_SLURM_PREFIX}/bin/qfw-slurm-driver" \
    && test -x /usr/lib64/slurm/spank_quantum.so \
    && test -x "${QFW_SLURM_PREFIX}/libexec/qfw-slurm/qfw-slurm-bb" \
    && test -f "${QFW_SLURM_PREFIX}/share/licenses/qfw-slurm/LICENSE" \
    && test -f "${QFW_SLURM_PREFIX}/share/man/man7/qfw-slurm.7" \
    && test -f "${QFW_SLURM_PREFIX}/share/man/man8/qfw-slurm-gateway.8" \
    && test -f "${QFW_SLURM_PREFIX}/share/man/man1/qfw-sinfo.1" \
    && test -f "${QFW_SLURM_PREFIX}/share/man/man1/qfw-squeue.1" \
    && test -f "${QFW_SLURM_PREFIX}/share/qfw-slurm/config/plugin.conf.example" \
    && "${QFW_IMAGE_VENV}/bin/python" -c \
        'import qfw_slurm_gateway, qfw_slurm_inspect' \
    && test -x "${QFW_IMAGE_VENV}/bin/qfw-sinfo" \
    && test -x "${QFW_IMAGE_VENV}/bin/qfw-squeue" \
    && rm -rf "${QFW_SLURM_SOURCE}" "${QFW_SLURM_BUILD}"

ENV QFW_IMAGE_PREFIX=${QFW_IMAGE_PREFIX} \
    QFW_IMAGE_VENV=${QFW_IMAGE_VENV} \
    QFW_PREFIX=${QFW_IMAGE_PREFIX} \
    QFW_VENV=${QFW_IMAGE_VENV} \
    QFW_SLURM_PREFIX=${QFW_SLURM_PREFIX} \
    NWQSIM_PREFIX=${NWQSIM_PREFIX} \
    TNQVM_PREFIX=${TNQVM_PREFIX} \
    QRMI_PREFIX=${QRMI_PREFIX} \
    QRMI_VERSION=${QRMI_VERSION} \
    MODULEPATH=/etc/modulefiles:/usr/share/Modules/modulefiles:/usr/share/modulefiles \
    LD_LIBRARY_PATH=${OMPI_PREFIX}/lib:${OMPI_PREFIX}/lib64:${QRMI_PREFIX}/lib:${LD_LIBRARY_PATH}

COPY modulefiles /etc/modulefiles
RUN set -ex \
    && env -i PATH=/usr/share/Modules/bin:/usr/bin:/bin \
        MODULEPATH=/etc/modulefiles:/usr/share/Modules/modulefiles \
        modulecmd sh load libfabric openmpi nwqsim \
        >/tmp/qfw-simulator-environment.sh \
    && . /tmp/qfw-simulator-environment.sh \
    && command -v prte \
    && command -v pterm \
    && command -v circuit_runner.nwqsim \
    && rm -f /tmp/qfw-simulator-environment.sh

# TJN: Add a basic cgroup.conf b/c appears to be needed now
COPY cgroup.conf /etc/slurm/cgroup.conf

COPY slurm.conf /etc/slurm/slurm.conf
COPY slurmdbd.conf /etc/slurm/slurmdbd.conf
COPY rest.conf /etc/slurm/rest.conf
COPY gres.conf /etc/slurm/gres.conf
COPY config/qfw-slurm/burst_buffer.conf /etc/slurm/burst_buffer.conf
COPY config/qfw-slurm/burst-buffer.lua.conf /etc/openqse/qfw-slurm/burst-buffer.lua.conf
COPY config/qfw-slurm/resources.lua /etc/openqse/qfw-slurm/resources.lua
COPY config/qfw-slurm/plugin.conf /etc/openqse/qfw-slurm/plugin.conf
COPY config/qfw-slurm/gateway.yaml /etc/openqse/qfw-slurm/gateway.yaml
COPY config/qfw-slurm/plugstack.conf /etc/slurm/plugstack.conf
RUN set -x \
    && groupadd -r qfw-slurm \
    && useradd -r -g qfw-slurm -d /var/lib/qfw-slurm-gateway \
        -s /sbin/nologin qfw-slurm \
    && install -o root -g root -m 0644 \
        "${QFW_SLURM_PREFIX}/share/qfw-slurm/slurm/job_submit.lua" \
        /etc/slurm/job_submit.lua \
    && install -o root -g root -m 0644 \
        "${QFW_SLURM_PREFIX}/share/qfw-slurm/slurm/burst_buffer.lua" \
        /etc/slurm/burst_buffer.lua \
    && openssl rand -hex 32 > /etc/slurm/jwt.key \
    && chown slurm:slurm /etc/slurm/slurm.conf \
    && chown slurm:slurm /etc/slurm/jwt.key \
    && chown slurm:slurm /etc/slurm/rest.conf \
    && chown slurm:slurm /etc/slurm/gres.conf \
    && chown slurm:slurm /etc/slurm/slurmdbd.conf \
    && chown root:root /etc/slurm/job_submit.lua \
        /etc/slurm/burst_buffer.lua /etc/slurm/burst_buffer.conf \
        /etc/slurm/plugstack.conf /etc/openqse/qfw-slurm/resources.lua \
        /etc/openqse/qfw-slurm/burst-buffer.lua.conf \
    && chown root:slurm /etc/openqse/qfw-slurm/plugin.conf \
    && chown root:qfw-slurm /etc/openqse/qfw-slurm/gateway.yaml \
    && chmod 0644 /etc/slurm/job_submit.lua /etc/slurm/burst_buffer.lua \
        /etc/slurm/burst_buffer.conf /etc/slurm/plugstack.conf \
        /etc/openqse/qfw-slurm/resources.lua \
    && chmod 0640 /etc/openqse/qfw-slurm/plugin.conf \
        /etc/openqse/qfw-slurm/gateway.yaml \
    && chmod 600 /etc/slurm/jwt.key \
    && chmod 600 /etc/slurm/slurmdbd.conf \
    && test -x /usr/lib64/slurm/job_submit_lua.so \
    && test -x /usr/lib64/slurm/burst_buffer_lua.so \
    && test -x /usr/lib64/slurm/spank_quantum.so \
    && test -f /etc/slurm/job_submit.lua \
    && test -f /etc/slurm/burst_buffer.lua \
    && test -f /etc/openqse/qfw-slurm/plugin.conf

RUN set -x \
    &&  useradd -r -g users --uid=1010 -m -c "Solomon Grundy" sgrundy

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY tools/qfw-site-services /usr/local/sbin/qfw-site-services
COPY man/man8/qfw-site-services.8 /usr/local/share/man/man8/qfw-site-services.8
RUN chmod 0755 /usr/local/sbin/qfw-site-services \
    && chmod 0644 /usr/local/share/man/man8/qfw-site-services.8
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

CMD ["slurmdbd"]
