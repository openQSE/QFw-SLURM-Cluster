#!/usr/bin/env python3
"""Write a Pasqal Cloud login or token and the project to a private env file.

QFw hands a QPM service's PASQAL_USERNAME and PASQAL_PASSWORD to QRMI, which
logs in to Pasqal Cloud itself and renews the token as it expires. This writes

    PASQAL_USERNAME=<username>
    PASQAL_PASSWORD=<password>
    QFW_PASQAL_PROJECT_ID=<project>

to an owner-only file in `docker exec --env-file` format, which
run_pulser_example.sh hands to the QPM service, so the login never appears
on a command line. It prints the file's path and never the login.

Each value is read from the environment first, then from ~/.pasqal/config
(the file pasqal-cloud and QRMI read):

    PASQAL_USERNAME     with PASQAL_PASSWORD, the login
    PASQAL_TOKEN        a token, which takes precedence over the login
    PASQAL_PROJECT_ID   the project the jobs are billed to

    ~/.pasqal/config:   username=..., password=..., token=..., project_id=...

A token is passed as QFW_API_KEY instead of the login: an exported
PASQAL_TOKEN always, a token= in the file only when there is no username and
password. QRMI cannot renew a token, so the run fails once it expires.

Usage: pasqal_login.py [OUTPUT]   (default: a fresh file in a private
                                   temporary directory)
"""

import os
import pathlib
import sys
import tempfile


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


def main():
	config = read_config()

	def setting(env, key):
		return os.environ.get(env) or config.get(key)

	project = setting("PASQAL_PROJECT_ID", "project_id")
	username = setting("PASQAL_USERNAME", "username")
	password = setting("PASQAL_PASSWORD", "password")
	token = os.environ.get("PASQAL_TOKEN")
	if not token and username and password:
		login = f"PASQAL_USERNAME={username}\nPASQAL_PASSWORD={password}\n"
	elif token or config.get("token"):
		login = f"QFW_API_KEY={token or config['token']}\n"
	else:
		sys.exit("no Pasqal Cloud login: set PASQAL_USERNAME and "
			 "PASQAL_PASSWORD, or PASQAL_TOKEN, or write them to "
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
		handle.write(f"{login}QFW_PASQAL_PROJECT_ID={project}\n")
	print(path)


if __name__ == "__main__":
	main()
