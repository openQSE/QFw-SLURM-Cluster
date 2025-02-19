# TJN NOTES

2025.02.18
----------
 - Figured out that nodes c1 and c2 failing b/c of cgroup settings
   missing and assumed `TaskPlugin=task/none` was not sufficient
   to ignore this need.  Fix was to add a `/etc/slurm/cgroup.conf`
   and then the `slurmd` will start. (see `docker logs c1`)

    ```
    ---> Starting the MUNGE Authentication service (munged) ...
    ---> Waiting for slurmctld to become active before starting slurmd...
    -- slurmctld is now active ...
    ---> Starting the Slurm Node Daemon (slurmd) ...
    slurmd: _read_slurm_cgroup_conf: No cgroup.conf file (/etc/slurm/cgroup.conf), using defaults
    slurmd: debug:  Log file re-opened
    slurmd: debug:  CPUs has been set to match sockets per node instead of threads CPUs=1:12(hw)
    slurmd: error: Node configuration differs from hardware: CPUs=1:12(hw) Boards=1:1(hw) SocketsPerBoard=1:1(hw) CoresPerSocket=1:6(hw) ThreadsPerCore=1:2(hw)
    slurmd: error: Couldn't find the specified plugin name for cgroup/v2 looking at all files
    slurmd: error: cannot find cgroup plugin for cgroup/v2
    slurmd: error: cannot create cgroup context for cgroup/v2
    slurmd: error: Unable to initialize cgroup plugin
    slurmd: error: slurmd initialization failed
    ```

 - Added 'cgroup.conf' to `update_slurmfiles.sh` script

 - At this point, I can now startup the cluster and things work.
   I left the hack in docker-entrypoint.sh in case i need it
   in future for debug hacks.
    - Example: edit "c1:" docker-compose.yml w/ `command: ["TJNXXX"]`
      and then you can `docker compose restart c1`)

 - Use `docker compose xxxx` (not `docker-compose xxxx`)
   (updated all the scripts accordingly)

 - Remember that SLURM tag/version is in `.env` file!!!

Old
---
 - Inspect failed container logs (e.g., `slurmctld` early exit)

   ```
     docker logs <ContainerID>
   ```

  Example:

   ```
    beaker: (tjn-main)$ docker ps -a
    CONTAINER ID   IMAGE                          COMMAND                  CREATED         STATUS                      PORTS      NAMES
    79dbfa583cdd   slurm-docker-cluster:24.05.3   "/usr/local/bin/dock…"   4 minutes ago   Up 26 seconds               6818/tcp   c1
    c1743e1c7d75   slurm-docker-cluster:24.05.3   "/usr/local/bin/dock…"   4 minutes ago   Up 27 seconds               6818/tcp   c2
    c9a7b05c9b13   slurm-docker-cluster:24.05.3   "/usr/local/bin/dock…"   4 minutes ago   Exited (1) 29 seconds ago              slurmctld
    d916b7c23cf8   slurm-docker-cluster:24.05.3   "/usr/local/bin/dock…"   4 minutes ago   Up 31 seconds               6819/tcp   slurmdbd
    380a987925ff   mariadb:10.11                  "docker-entrypoint.s…"   4 minutes ago   Up 32 seconds               3306/tcp   mysql
    beaker: (tjn-main)$ docker logs c9a7b05c9b13
    ---> Starting the MUNGE Authentication service (munged) ...
    ---> Waiting for slurmdbd to become active before starting slurmctld ...
    -- slurmdbd is not available.  Sleeping ...
    -- slurmdbd is not available.  Sleeping ...
    -- slurmdbd is now active ...
    ---> Starting the Slurm Controller Daemon (slurmctld) ...
    slurmctld: error: Ignoring obsolete FastSchedule=1 option. Please remove from your configuration.
    slurmctld: debug:  slurmctld log levels: stderr=debug2 logfile=debug2 syslog=quiet
    slurmctld: debug:  Log file re-opened
    slurmctld: debug:  auth/munge: init: loaded
    slurmctld: debug:  hash/k12: init: init: KangarooTwelve hash plugin loaded
    slurmctld: debug:  tls/none: init: tls/none loaded
    slurmctld: Not running as root. Can't drop supplementary groups
    slurmctld: debug2: slurmctld listening on 0.0.0.0:6817
    slurmctld: debug:  creating clustername file: /var/lib/slurmd/clustername
    slurmctld: error: Configured MailProg is invalid
    slurmctld: debug:  slurmscriptd: Got ack from slurmctld
    slurmctld: debug:  Initialization successful
    slurmctld: debug:  slurmctld: slurmscriptd fork()'d and initialized.
    slurmctld: debug:  _slurmscriptd_mainloop: started
    slurmctld: debug:  _slurmctld_listener_thread: started listening to slurmscriptd
    slurmctld: slurmctld version 24.05.3 started on cluster linux
    slurmctld: cred/munge: init: Munge credential signature plugin loaded
    slurmctld: select/cons_tres: init: select/cons_tres loaded
    slurmctld: select/linear: init: Linear node selection plugin loaded with argument 17
    slurmctld: fatal: Can't find plugin for select/cons_res
    beaker: (tjn-main)$
   ```
