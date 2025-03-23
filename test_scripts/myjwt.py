#
# Tiny script to do what would be done by standard `jwt` utility
# for encoding/decoding JWT tokens.
#

import jwt  # PyJWT
import time
import sys
import argparse

KEYFILE="_jwt.key"
THEUSER="sgrundy"

def do_encode():
    secret = open(KEYFILE, "r").read().strip()

    payload = {
            "sub": THEUSER,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600   # Expires in 1 hour
    }

    token = jwt.encode(payload, secret, algorithm="HS256")
    return token

def do_decode(token_file):
    token = open(token_file, "r").read().strip()

    return jwt.decode(token, options={'verify_signature': False})



# MAIN

p = argparse.ArgumentParser(description="TinyJWT tool")
p.add_argument("-d", "--decode",
               help="Decode given fileame")
args = p.parse_args()

if args.decode:
#if sys.argc > 3 and sys.argv[1] == "decode":
    r = do_decode(args.decode)
    print(r)
else:
    r = do_encode()
    print(r)

##secret = open("slurm.jwks", "r").read().strip()
#secret = open("_jwt.key", "r").read().strip()
#
#payload = {
#        "sub": "root",
#        "iat": int(time.time()),
#        "exp": int(time.time()) + 3600   # Expires in 1 hour
#}
#
#token = jwt.encode(payload, secret, algorithm="HS256")
#print(token)
