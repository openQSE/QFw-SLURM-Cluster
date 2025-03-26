# TJN NOTES

2025.03.25
----------
 - Finally got full slurmrestd GET (nodes) and POST (job/submit) to work!
   Was a few minor (dumb) mistakes and finally found issues.
   See: rest-testing/curl-post.sh, rest-testing/curl-get.sh, rest-testing/tiny-submit.py
 - Update Dockerfile to include configs and related by default
 - Fix port exposure problem, use 'ports' to expose to host.
   The 'expose' is just so can see between containers.
 - Add a script to update all the rest/config bits on fresh build.
   To just list status of key files:
   ```
     ./update_rest_stuff.sh
   ```
   To list status of key files and copy/update/restart containers:
   ```
    ./update_rest_stuff.sh copy
   ```
 - To disable silly macOS docker extra text hints,
   `export DOCKER_CLI_HINTS=false`

 - Added the "tiny-compute" pieces to cosched/compute_mgr_service and client2
   see: https://code.ornl.gov/intersect/coscheduling/cosched


2025.03.23
----------
 - Add few more slurmrestd related configure options to Dockerfile
   "--with-http-parser=/usr --with-yaml=/usr ",
   and libyaml-devel to packages
 - Note, discovered that slurmrestd does not want to be run as root,
   but as slurm user.   With latest changes, can now run the 'scontrol
   token' to get a token on slurmctld container.
   (Still need to diagnose problems with using slurmrestd endpoint.)
 - Finally got things working for slurmrestd.  Needed to startup
   as slurm user (like slurmctld, etc.) in entrypoint script.
   I also added `slurm_jobdir:/data` in docker-compose.  The key
   is that `scontrol show config` or the like must be able to run
   from slurmrestd container.  If not, then nothing will work.
 - Add a 'scurl' alias to run the curl command inside slurmrestd container
 - Can also run from the 'slurmctld' container like the following:
   ```
     (venv) fozzie:$ ./do_dropin.sh
     [root@slurmctld /]# su sgrundy
     [sgrundy@slurmctld /]$ export $(scontrol token)
     [sgrundy@slurmctld /]$ curl -H "Authorization: Bearer $SLURM_JWT" \
          http://slurmrestd:6820/slurm/v0.0.41/nodes
   ```
 - The curl based GET commands are working.  However, the POST actions
   are failing to work.  I verified this with both curl.  It also
   seems like the GET based actions may have problems when I use the Python
   approach, even if the header seems to be setup just like curl case.
    - TODO: Why POST not work.
    - TODO: Why GET/POST not work for python request example

2025.03.23
----------
 - Add a dummy user "sgrundy" for testing
 - Add `test_scripts/` dir with couple commands
   to speed up reservation testing. Include an aliases file
   for easy access to docker based slurm commands.
 - Add rest.conf and include in updatefiles script
 - create myjwt.py tiny script for encode/decode JWT tokens
 - add curltest2.sh script for testing the slurmrestd endpoint (still busted)

2025.03.12
----------
 - If goof a SLURM config file (e.g., slurmctld service will not startup),
   you can update slurm.conf manually in container like this:
   ```
     docker cp slurm.conf slurmctld:/etc/slurm/slurm.conf
   ```

 - Add `libjwt-devel` to Dockerfile(s) and `--with-jwt` to slurm configure
   so we get `auth_jwt` built for use with slurmrestd.
   Also, add `rest.conf` and add to `update_slurmfiles.sh`

 - Need to generate JWT token, for now create outside and copy into containers.
   ```
      openssl rand -hex 32 > /etc/slurm/jwt.key
      chmod 600 /etc/slurm/jwt.key
      docker cp jwt.key slurmctld:/etc/slurm/jwt.key
      docker cp jwt.key slurmrestd:/etc/slurm/jwt.key
      docker exec slurmctld  chown slurm:slurm /etc/slurm/jwt.key
      docker exec slurmrestd chown slurm:slurm /etc/slurm/jwt.key
   ```

 - Test command
   ```
    curl -k -H "X-SLURM-USER-TOKEN: $(cat /etc/slurm/jwt.key)" http://localhost:6820/slurm/v0.0.42/nodes
   ```

2025.02.21
----------
 - RockyLinux using coreutils-single (multi-binary), missing /bin/ps,
   FIX: `yum install procps-ng` to get `ps`

2025.02.19
----------
 - adjust slurm.conf to have more CPUs per node.  Not seeing full
   set of cores (just 2 per node), but configured to have 8 CPUs.
   (see: slurm.conf and check with `scontrol show node c1`)

 - add cgroup.conf COPY to Dockerfile so it is there by default
   (appears to be needed with 24.05.03)

 - fix Docker build error on my macOS laptop, failing 'docker compose build'
 - Brief: Getting curl certificate errors with rockylinux
   when try to get the mirror list during 'yum makecache'
   My HACK is to just disable SSL cert validation in a very
   heavy handed way.  Adding this to the initial RUN line of dockerfile:
    ```
    echo 'sslverify=false' >> /etc/yum.conf \
    ```
 - fix Docker build error on my macOS laptop, failing 'docker compose build'
   related to `gpg` within the `gosu` step.  Replace with curl instead.
   ```
    curl --insecure -fsSL "https://keys.openpgp.org/pks/lookup?op=get&search=0xB42F6819007F00F88E364FD4036A9C25BF357DD4" | gpg --import \
   ```

2025.02.18
----------
 - slurmrestd setup
    - TODO: next https://slurm.schedmd.com/jwt.html#setup

    - Added new docker-compose.yml entry and block in docker-entrypoint.sh
    - Hacks for starting the slurmrestd in container without various namespaces
      stuff `export SLURMRESTD_SECURITY=disable_unshare_sysv,disable_unshare_files,disable_user_check`
      (See: `/usr/local/bin/docker-entrypoint.sh`)

    - Got the basic `slurmrestd` to startup but not able to get the
      authentication working so I can do curl requests.

    - See also: https://slurm.schedmd.com/rest_quickstart.html

    - Example command at stop point for today
      ```
        beaker: (tjn-main)$ docker exec -ti slurmrestd bash

          ...<snip>...

        [root@slurmrestd /]# env | grep SLURM
        SLURMRESTD_DEBUG=debug
        SLURMRESTD_SECURITY=disable_unshare_sysv,disable_unshare_files,disable_user_check
        [root@slurmrestd /]# slurmrestd -s list
        slurmrestd: debug:  slurm_conf_init: using config_file=/etc/slurm/slurm.conf
        slurmrestd: debug:  Reading slurm.conf file: /etc/slurm/slurm.conf
        slurmrestd: debug:  NodeNames=c[1-2] setting Sockets=Boards(1)
        slurmrestd: debug:  auth/munge: init: loaded
        slurmrestd: debug:  hash/k12: init: init: KangarooTwelve hash plugin loaded
        slurmrestd: debug:  tls/none: init: tls/none loaded
        slurmrestd: accounting_storage/slurmdbd: init: Accounting storage SLURMDBD plugin loaded
        slurmrestd: cred/munge: init: Munge credential signature plugin loaded
        slurmrestd: debug:  _plugrack_foreach: serializer plugin type:serializer/json path:/usr/lib64/slurm/serializer_json.so
        slurmrestd: debug:  _plugrack_foreach: serializer plugin type:serializer/url-encoded path:/usr/lib64/slurm/serializer_url_encoded.so
        slurmrestd: debug:  _plugrack_foreach: serializer plugin type serializer/json already loaded
        slurmrestd: debug:  _plugrack_foreach: data_parser plugin type:data_parser/v0.0.40 path:/usr/lib64/slurm/data_parser_v0_0_40.so
        slurmrestd: debug:  _plugrack_foreach: data_parser plugin type:data_parser/v0.0.39 path:/usr/lib64/slurm/data_parser_v0_0_39.so
        slurmrestd: debug:  _plugrack_foreach: data_parser plugin type:data_parser/v0.0.41 path:/usr/lib64/slurm/data_parser_v0_0_41.so
        Possible OpenAPI plugins:
        slurmrestd: debug:  _plugrack_foreach: serializer plugin type serializer/json already loaded
        openapi/v0.0.39
        openapi/dbv0.0.39
        openapi/slurmctld
        openapi/slurmdbd
        [root@slurmrestd /]#
      ```

 - Add `LaunchParameters=use_interactive_step` to slurm.conf to land
   on first node in allocation when using `salloc` w/ interactive shell.

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

    - **NOTE:** May want to also try this slightly simpler version (**untested**)
      ```
      CgroupAutomount=yes
      CgroupPlugin=cgroup/v1
      ConstrainCores=no
      ConstrainRAMSpace=no
      ```

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
