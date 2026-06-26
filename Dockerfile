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

#    && gpg --batch --keyserver hkps://keys.openpgp.org --recv-keys B42F6819007F00F88E364FD4036A9C25BF357DD4 \

RUN set -ex \
    && wget -O /usr/local/bin/gosu "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-amd64" \
    && wget -O /usr/local/bin/gosu.asc "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-amd64.asc" \
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
    && tar -xzf osu-micro-benchmarks-${OSU_OMB_VERSION}.tar.gz \
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
    && rm -rf /var/cache/yum \
    && pip3 install scons

ARG QFW_REPO=https://github.com/openQSE/QFw.git
ARG QFW_BUILD_JOBS=4
ARG QFW_IMAGE_BASE=/opt/qfw/qhpc
ARG QFW_IMAGE_BUILD_VERSION=image

RUN set -ex \
    && mkdir -p "${QFW_IMAGE_BASE}/rocm" \
    && git -c url.https://github.com/.insteadOf=git@github.com: \
        clone --recursive "${QFW_REPO}" "${QFW_IMAGE_BASE}/QFw" \
    && python3 -m venv "${QFW_IMAGE_BASE}/venv" \
    && "${QFW_IMAGE_BASE}/venv/bin/python" -m pip install --upgrade \
        pip setuptools wheel \
    && "${QFW_IMAGE_BASE}/venv/bin/python" -m pip install \
        -r "${QFW_IMAGE_BASE}/QFw/setup/build-requirements.txt" \
    && { \
        echo "runtime-mode: container"; \
        echo "mpi-transport-mode: auto"; \
        echo "base-dir: ${QFW_IMAGE_BASE}"; \
        echo "python-venv-activate: ${QFW_IMAGE_BASE}/venv/bin/activate"; \
        echo "libfabric-install: ${LIBFABRIC_PREFIX}"; \
        echo "mpi-install: ${OMPI_PREFIX}"; \
        echo "dev-install: ${QFW_IMAGE_BASE}/rocm"; \
        echo "dev-version: 0.0.0"; \
        echo "build-jobs: ${QFW_BUILD_JOBS}"; \
        echo "qfw-dep-build-version: ${QFW_IMAGE_BUILD_VERSION}"; \
    } > "${QFW_IMAGE_BASE}/QFw/setup/qfw_config_image.yaml" \
    && cd "${QFW_IMAGE_BASE}/QFw/setup" \
    && "${QFW_IMAGE_BASE}/venv/bin/python" ./qfw_configure \
        -c qfw_config_image.yaml \
    && QFW_BUILD_JOBS="${QFW_BUILD_JOBS}" ./qfw_build.sh

ENV QFW_IMAGE_BASE=${QFW_IMAGE_BASE} \
    QFW_IMAGE_QFW=${QFW_IMAGE_BASE}/QFw \
    QFW_IMAGE_VENV=${QFW_IMAGE_BASE}/venv \
    QFW_IMAGE_BUILD_VERSION=${QFW_IMAGE_BUILD_VERSION} \
    QFW_BUILD_JOBS=${QFW_BUILD_JOBS}

ENV PATH=${OMPI_PREFIX}/bin:${LIBFABRIC_PREFIX}/bin:${QFW_IMAGE_BASE}/QFw/bin:${PATH}

ENV LD_LIBRARY_PATH=${OMPI_PREFIX}/lib:${LIBFABRIC_PREFIX}/lib:${QFW_IMAGE_BASE}/QFw/DEFw/src:${QFW_IMAGE_BASE}/install/${QFW_IMAGE_BUILD_VERSION}/TNQVM/exatn/lib:${QFW_IMAGE_BASE}/install/${QFW_IMAGE_BUILD_VERSION}/TNQVM/xacc/lib:${QFW_IMAGE_BASE}/build/${QFW_IMAGE_BUILD_VERSION}/TNQVM/tnqvm/plugins:${QFW_IMAGE_BASE}/install/${QFW_IMAGE_BUILD_VERSION}/NWQSIM/lib

# ----------------------------------------------------------------------
# QRMI / QDMI shim dependencies
#
# Lower-level interface libraries the QFw front-end shim will route to;
# see shared-dir/QFw/docs/qpu-frontend-contract.md. Placed after the QFw
# build so iteration here does not invalidate the heavy QFw layer.
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
# QRMI 0.17.2 (2026-06-18) fixes a vulnerability in PyO3, the dependency
# behind the Python bindings (the part loaded into the QFw venv); upstream
# strongly recommends upgrading anyone using the bindings. spank-plugins stays
# at 0.7.0 -- still the latest SPANK release, it is C and does not use PyO3, and
# its build links the locally-cloned QRMI (0.17.2) via -DQRMI_ROOT.
ARG QRMI_REPO=https://github.com/qiskit-community/qrmi.git
ARG QRMI_VERSION=0.17.2
ARG QRMI_PREFIX=/opt/qfw/qrmi
ARG QRMI_SPANK_REPO=https://github.com/qiskit-community/spank-plugins.git
ARG QRMI_SPANK_REF=0.7.0
RUN set -ex \
    && git clone --depth=1 --branch "${QRMI_VERSION}" "${QRMI_REPO}" /tmp/qrmi \
    && cd /tmp/qrmi \
    && cargo build --locked --release --lib \
    && mkdir -p "${QRMI_PREFIX}/lib" "${QRMI_PREFIX}/include" \
    && cp target/release/libqrmi.so "${QRMI_PREFIX}/lib/" \
    && (cp target/release/libqrmi.a "${QRMI_PREFIX}/lib/" 2>/dev/null || true) \
    && cp qrmi.h "${QRMI_PREFIX}/include/" \
    && "${QFW_IMAGE_VENV}/bin/pip" install --no-cache-dir "qrmi==${QRMI_VERSION}" \
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

# MQT Core (Munich Quantum Toolkit) — provides the `mqt.core` package, incl. the
# FoMaC layer and the Qiskit QDMIBackend that iqm-qdmi[qiskit] builds on. It is
# normally pulled in as a transitive wheel of iqm-qdmi; built from source here,
# BEFORE iqm-qdmi, from a fork branch that adds a FoMaC accessor for QDMI custom
# device properties (Device.custom_property) — the path that surfaces
# QDMI-on-IQM's raw IQM data to Python. Installing it first means pip keeps this
# build instead of replacing it with the PyPI wheel when iqm-qdmi is installed.
#
# The branch is ahead of the v3.6.1 tag, so setuptools-scm would otherwise stamp
# a pre-release version (3.6.2.devN); SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MQT_CORE
# forces 3.6.1 so the build still satisfies iqm-qdmi's mqt-core pin.
ARG MQT_CORE_REPO=https://github.com/DougSO/mqt-core.git
ARG MQT_CORE_REF=qdmi-raw-passthrough
RUN set -ex \
    && CMAKE_BUILD_PARALLEL_LEVEL="$(nproc)" \
       SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MQT_CORE=3.6.1 \
       "${QFW_IMAGE_VENV}/bin/pip" install --no-cache-dir \
        "mqt-core @ git+${MQT_CORE_REPO}@${MQT_CORE_REF}"

# QDMI-on-IQM — IQM's official QDMI implementation, installed into the QFw venv.
# The 'qiskit' extra wires up the Qiskit backend.
#
# Built from source from a fork branch that adds a raw-device-data passthrough:
# the IQM REST payloads are exposed via QDMI_DEVICE_PROPERTY_CUSTOM1 and surfaced
# in Python as IQMBackend.raw_device_config(), so the shim can feed QDMI's raw
# IQM data to qhw-iqm directly, the way the QRMI driver does, instead of
# translating a Qiskit Target. Reading it relies on the MQT Core FoMaC accessor
# built above.
#
# The source build needs CMake >= 3.24 (Rocky 10 dnf provides 3.30), ninja, and
# g++ — all installed above; scikit-build-core (PEP 517) drives the CMake build
# and FetchContent pulls the QDMI headers at build time. Pin IQM_QDMI_REF to a
# commit SHA for reproducible images once the branch settles.
ARG IQM_QDMI_REPO=https://github.com/DougSO/QDMI-on-IQM.git
ARG IQM_QDMI_REF=qdmi-raw-passthrough
RUN set -ex \
    && "${QFW_IMAGE_VENV}/bin/pip" install --no-cache-dir \
        "iqm-qdmi[qiskit] @ git+${IQM_QDMI_REPO}@${IQM_QDMI_REF}"

ENV QRMI_PREFIX=${QRMI_PREFIX} \
    LD_LIBRARY_PATH=${QRMI_PREFIX}/lib:${LD_LIBRARY_PATH}

COPY modulefiles /etc/modulefiles

# TJN: Add a basic cgroup.conf b/c appears to be needed now
COPY cgroup.conf /etc/slurm/cgroup.conf

COPY slurm.conf /etc/slurm/slurm.conf
COPY slurmdbd.conf /etc/slurm/slurmdbd.conf
COPY rest.conf /etc/slurm/rest.conf
COPY gres.conf /etc/slurm/gres.conf
RUN set -x \
    && openssl rand -hex 32 > /etc/slurm/jwt.key \
    && chown slurm:slurm /etc/slurm/slurm.conf \
    && chown slurm:slurm /etc/slurm/jwt.key \
    && chown slurm:slurm /etc/slurm/rest.conf \
    && chown slurm:slurm /etc/slurm/gres.conf \
    && chown slurm:slurm /etc/slurm/slurmdbd.conf \
    && chmod 600 /etc/slurm/jwt.key \
    && chmod 600 /etc/slurm/slurmdbd.conf

RUN set -x \
    &&  useradd -r -g users --uid=1010 -m -c "Solomon Grundy" sgrundy

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

CMD ["slurmdbd"]
