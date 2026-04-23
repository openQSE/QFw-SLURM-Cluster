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
       libtool \
       m4 \
       ncurses-devel \
       openssl \
       openssl-devel \
       perl \
       patch \
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
    && ./configure --prefix="${OMPI_PREFIX}" --with-libfabric="${LIBFABRIC_PREFIX}" CC="${CC}" CXX="${CXX}" FC="${FC}" \
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
