#!/bin/bash

set -xe

docker compose stop

if [ "$1" == "delete" ] ; then
    docker compose down -v
fi
