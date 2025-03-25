
 - Show support features:
   ```
    bash-4.4$ SLURM_JWT=daemon slurmrestd -s list
    Possible OpenAPI plugins:
    openapi/slurmdbd
    openapi/dbv0.0.39
    openapi/slurmctld
    openapi/v0.0.39

    bash-4.4$ SLURM_JWT=daemon slurmrestd -d list
    Possible data_parser plugins:
    data_parser/v0.0.39
    data_parser/v0.0.40
    data_parser/v0.0.41

    bash-4.4$ SLURM_JWT=daemon slurmrestd -a list
    Possible REST authentication plugins:
    rest_auth/jwt
    rest_auth/local

    bash-4.4$ whoami
    slurm
   ```

 - Show supported the supported data parsers.
   ```
       [root@slurmrestd /]# su slurm
       [slurm@slurmrestd /]$ slurmrestd -d list
       Possible data_parser plugins:
       data_parser/v0.0.39
       data_parser/v0.0.40
       data_parser/v0.0.41
   ```

 - Generate the OpenAPI spec for given version
   ```
       [slurm@slurmrestd /]$ env SLURM_CONF=/dev/null slurmrestd \
                -d v0.0.41 \
                -s slurmdbd,slurmctld \
                --generate-openapi-spec > /tmp/v41.json
   ```
