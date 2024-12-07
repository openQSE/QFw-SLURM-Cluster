#!/bin/bash

wait_for_slurmdbd_ready() {
   str="slurmdbd: slurmdbd version"

   while true; do
    if docker compose logs | grep -q "$str" ; then
        echo "SlurmDBD ready!"
        break
    else
        echo "Waiting on SlurmDBD..."
        sleep 2
    fi
   done
}

set -xe

docker compose up -d

wait_for_slurmdbd_ready

sleep 5

./register_cluster.sh
