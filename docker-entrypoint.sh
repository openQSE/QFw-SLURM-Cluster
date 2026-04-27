#!/bin/bash
# VERSION: 3
set -e

ensure_root_ssh() {
    install -d -m 0700 /root/.ssh

    if [ ! -f /root/.ssh/id_ed25519 ]; then
        ssh-keygen -q -t ed25519 -N "" -f /root/.ssh/id_ed25519
    fi

    cat > /root/.ssh/config <<'EOF'
Host *
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
EOF

    cp /root/.ssh/id_ed25519.pub /root/.ssh/authorized_keys
    chmod 0600 /root/.ssh/id_ed25519 /root/.ssh/authorized_keys /root/.ssh/config
    chmod 0644 /root/.ssh/id_ed25519.pub
}

ensure_sshd_host_keys() {
    if [ ! -f /etc/ssh/ssh_host_ed25519_key ]; then
        ssh-keygen -A
    fi

    install -d -m 0755 /run/sshd
    cat > /etc/ssh/sshd_config.d/qfw-cluster.conf <<'EOF'
PermitRootLogin yes
PasswordAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
EOF
}

start_sshd() {
    ensure_root_ssh
    ensure_sshd_host_keys

    if ! pgrep -x sshd >/dev/null 2>&1; then
        /usr/sbin/sshd
    fi
}

ensure_munge_key() {
    install -d -m 0700 /etc/munge
    install -d -o munge -g munge -m 0755 /run/munge
    install -d -o munge -g munge -m 0700 /var/log/munge

    if [ ! -f /etc/munge/munge.key ]; then
        dd if=/dev/urandom bs=1 count=1024 of=/etc/munge/munge.key status=none
    fi

    chown -R munge:munge /etc/munge
    chmod 0700 /etc/munge
    chmod 0400 /etc/munge/munge.key
}


if [ "$1" = "TJNXXX" ]
then
    echo "TJNXXX DBG"
    ensure_munge_key
    echo "---> Starting the MUNGE Authentication service (munged) ..."
    gosu munge /usr/sbin/munged

    echo "TJNXXX DBG"
    echo "---> Waiting for slurmctld to become active before starting slurmd..."

    until 2>/dev/null >/dev/tcp/slurmctld/6817
    do
        echo "-- slurmctld is not available.  Sleeping ..."
        sleep 2
    done
    echo "TJNXXX DBG"
    echo "-- slurmctld is now active ..."

    echo "DBGXXX"
    echo "---> Starting the Slurm Node Daemon (slurmd) ..."
#    exec /usr/sbin/slurmd -Dvvv
    echo "TJN: HACK to avoid starting slurmd and just start - DONE"

    echo "TJN: RUN SLEEP INFINITY"
    exec /usr/bin/sleep infinity
    echo "TJNXXX DBG"

fi


if [ "$1" = "slurmdbd" ]
then
    start_sshd
    ensure_munge_key
    echo "---> Starting the MUNGE Authentication service (munged) ..."
    gosu munge /usr/sbin/munged

    echo "---> Starting the Slurm Database Daemon (slurmdbd) ..."

    {
        . /etc/slurm/slurmdbd.conf
        until echo "SELECT 1" | mysql -h $StorageHost -u$StorageUser -p$StoragePass 2>&1 > /dev/null
        do
            echo "-- Waiting for database to become active ..."
            sleep 2
        done
    }
    echo "-- Database is now active ..."

    exec gosu slurm /usr/sbin/slurmdbd -Dvvv
fi

if [ "$1" = "slurmctld" ]
then
    start_sshd
    ensure_munge_key
    echo "---> Starting the MUNGE Authentication service (munged) ..."
    gosu munge /usr/sbin/munged

    echo "---> Waiting for slurmdbd to become active before starting slurmctld ..."

    until 2>/dev/null >/dev/tcp/slurmdbd/6819
    do
        echo "-- slurmdbd is not available.  Sleeping ..."
        sleep 2
    done
    echo "-- slurmdbd is now active ..."

    echo "---> Starting the Slurm Controller Daemon (slurmctld) ..."
    if /usr/sbin/slurmctld -V | grep -q '17.02' ; then
        exec gosu slurm /usr/sbin/slurmctld -Dvvv
    else
        exec gosu slurm /usr/sbin/slurmctld -i -Dvvv
    fi
fi

if [ "$1" = "slurmd" ]
then
    start_sshd
    ensure_munge_key
    echo "---> Starting the MUNGE Authentication service (munged) ..."
    gosu munge /usr/sbin/munged

    echo "---> Waiting for slurmctld to become active before starting slurmd..."

    until 2>/dev/null >/dev/tcp/slurmctld/6817
    do
        echo "-- slurmctld is not available.  Sleeping ..."
        sleep 2
    done
    echo "-- slurmctld is now active ..."

    echo "---> Starting the Slurm Node Daemon (slurmd) ..."
    exec /usr/sbin/slurmd -Dvvv
fi

if [ "$1" = "slurmrestd" ]
then
    start_sshd
    ensure_munge_key
    echo "---> Starting the MUNGE Authentication service (munged) ..."
    gosu munge /usr/sbin/munged

    echo "---> Waiting for slurmctld to become active before starting slurmrestd..."

    until 2>/dev/null >/dev/tcp/slurmctld/6817
    do
        echo "-- slurmctld is not available.  Sleeping ..."
        sleep 2
    done
    echo "-- slurmctld is now active ..."

    #export SLURM_JWT=''
    export SLURM_JWT=daemon
    export SLURMRESTD_DEBUG=debug

    #export SLURM_REST_API_AUTH=jwt
    #export SLURM_REST_API_AUTH_JWT_SECRET="/etc/slurm/jwt.key"

    # XXX: Disable lots of security checks b/c running in devel container
    #  (Note: removed `disable_user_check` or get error with slurm-25.05.1)
    export SLURMRESTD_SECURITY=disable_unshare_sysv,disable_unshare_files

#    openssl rand -hex 32 > /etc/slurm/jwt.key
#    chmod 600 /etc/slurm/jwt.key

    echo "---> Starting the Slurm REST Daemon (slurmrestd) ..."
    exec gosu nobody /usr/sbin/slurmrestd -vvvvv 0.0.0.0:6820
fi

start_sshd
exec "$@"
