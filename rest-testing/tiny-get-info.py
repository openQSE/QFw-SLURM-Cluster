import requests
import json
import os
import argparse
import pprint

VERBOSE=False
#SLURM_API_URL = "http://localhost:6820/slurm/v0.0.39/job"
SLURM_API_URL = "http://localhost:6820/slurm/v0.0.43/job"

p = argparse.ArgumentParser(description="tiny rest tool")
p.add_argument("-j", "--jobid",
               required=True,
               type=int,
               help="JobID to get info about.")
p.add_argument("-v", "--verbose",
               action="store_true",
               help="Enable verbose output.")
args = p.parse_args()

if 'SLURM_JWT' in os.environ:
    MY_TOKEN = os.environ.get('SLURM_JWT')
    if args.verbose:
        print(f"FOUND TOKEN IN ENV:\n {MY_TOKEN}")
else:
    MY_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NTEwNjg5MTYsImlhdCI6MTc1MTA2NzExNiwic3VuIjoicm9vdCJ9.u6SG176t9FEkon7ArtWTqDBT2ROYhglvnkvoYQvoZPw"

    if args.verbose:
        print(f"TRY A DEFAULT TOKEN:\n {MY_TOKEN}")


HEADERS = {
        "Content-type": "application/json",
        "X-SLURM-USER-NAME": "sgrundy",
        "X-SLURM-USER-TOKEN": MY_TOKEN,
}


# Submit the job
if args.verbose:
    print(f"Get info for JobID: {args.jobid}")

url=SLURM_API_URL + "/" + str(args.jobid)

print(f"DBG: url: {url}")
response = requests.get(url, headers=HEADERS)

if response.status_code == 200:
    if args.verbose:
        print("Job submitted successfully!")
    print(json.dumps(response.json(), indent=4))
    #data = json.loads(response.json())  # Convert JSON string to a dictionary
    data = response.json()

    jid = data['jobs'][0]['job_id']
    print(f"DBG: jid={jid}")

    jstate = data['jobs'][0]['job_state']
    job_stderr_file = data['jobs'][0]['standard_error']
    job_stdout_file = data['jobs'][0]['standard_output']
    print(f"DBG: Job_ID: {jid} Job_State: {jstate}  Response-Code: {response.status_code}")
    print(f"DBG: job_stdout: {job_stdout_file}")
    print(f"DBG: job_stderr: {job_stderr_file}")

    if data['jobs'][0]['job_resources']:
        #nodename = data['jobs'][0]['job_resources']['allocated_nodes'][0]['nodename']
        nodes = data['jobs'][0]['job_resources']['nodes']
        print(f"DBG: Nodes info:")
        pprint.pprint(nodes)

else:
    print(f"Failed to submit job: {response.status_code} {response.text}")

print("Done")
