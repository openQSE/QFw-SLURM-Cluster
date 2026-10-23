#!/usr/bin/env python3
"""Write a Pasqal Cloud token and project to a private env file.

QFw's Pasqal devices take a Pasqal Cloud token, not a
username and password, and the token expires. This fetches a fresh one from
the caller's own Pasqal Cloud login and writes

    QFW_API_KEY=<token>
    QFW_PASQAL_PROJECT_ID=<project>

to an owner-only file in `docker exec --env-file` format, which
run_pulser_example.sh hands to the QPM service, so the token never appears
on a command line. It prints the file's path and never the token.

Each value is read from the environment first, then from ~/.pasqal/config
(the file pasqal-cloud and QRMI read):

    PASQAL_TOKEN        an existing token, used as is
    PASQAL_USERNAME     with PASQAL_PASSWORD, exchanged for a token
    PASQAL_PROJECT_ID   the project the jobs are billed to

    ~/.pasqal/config:   username=..., password=..., token=..., project_id=...,
                        optionally auth_endpoint=...

The token is PASQAL_TOKEN when it is set; otherwise a fresh one from the
username and password; a token= in the config file only when there is no
login to exchange, since a stored token may have expired.

Usage: pasqal_token.py [OUTPUT]   (default: a fresh file in a private
                                   temporary directory)
"""

import json
import os
import pathlib
import sys
import tempfile
import urllib.parse
import urllib.request

# Pasqal Cloud's public login client, as pasqal-cloud and QRMI use it.
AUTH_ENDPOINT = "https://authenticate.pasqal.cloud/oauth/token"
AUTH_FIELDS = {
	"grant_type": "http://auth0.com/oauth/grant-type/password-realm",
	"realm": "pcs-users",
	"client_id": "PeZvo7Atx7IVv3iel59asJSb4Ig7vuSB",
	"audience": "https://apis.pasqal.cloud/account/api/v1",
}


def read_config():
	path = pathlib.Path.home() / ".pasqal" / "config"
	values = {}
	if path.is_file():
		for line in path.read_text(encoding="utf-8").splitlines():
			line = line.strip()
			if "=" in line and not line.startswith(("#", ";")):
				key, value = line.split("=", 1)
				values[key.strip().lower()] = value.strip().strip("'\"")
	return values


def login(username, password, endpoint):
	if not endpoint.startswith("http"):
		endpoint = "https://" + endpoint
	data = urllib.parse.urlencode(
		dict(AUTH_FIELDS, username=username, password=password)).encode()
	request = urllib.request.Request(endpoint, data=data)
	with urllib.request.urlopen(request, timeout=30) as response:
		return json.load(response)["access_token"]


def main():
	config = read_config()

	def setting(env, key):
		return os.environ.get(env) or config.get(key)

	project = setting("PASQAL_PROJECT_ID", "project_id")
	username = setting("PASQAL_USERNAME", "username")
	password = setting("PASQAL_PASSWORD", "password")
	token = os.environ.get("PASQAL_TOKEN")
	if not token and username and password:
		token = login(username, password,
			config.get("auth_endpoint") or AUTH_ENDPOINT)
	token = token or config.get("token")
	if not token:
		sys.exit("no Pasqal Cloud login: set PASQAL_TOKEN, or "
			 "PASQAL_USERNAME and PASQAL_PASSWORD, or write them to "
			 "~/.pasqal/config")
	if not project:
		sys.exit("no Pasqal Cloud project: set PASQAL_PROJECT_ID or "
			 "project_id in ~/.pasqal/config")

	if len(sys.argv) > 1:
		path = sys.argv[1]
	else:
		path = os.path.join(tempfile.mkdtemp(prefix="pasqal-"), "pasqal.env")
	fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
	# The mode above applies only to a file it creates.
	os.fchmod(fd, 0o600)
	with os.fdopen(fd, "w") as handle:
		handle.write(f"QFW_API_KEY={token}\nQFW_PASQAL_PROJECT_ID={project}\n")
	print(path)


if __name__ == "__main__":
	main()
