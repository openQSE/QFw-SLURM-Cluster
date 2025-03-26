import requests
import json
import os
import time
import argparse

def poll_job_status(url, headers, jobid, verbose=False):
    state = "UNKNOWN"

    if verbose:
        print(f"DBG:     url: {url}")
        print(f"DBG: headers: {headers}")
        print(f"DBG:   jobid: {jobid}")

    while True:
        if verbose:
            print(f"GET {url}")
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            job_info = response.json().get("jobs", [{}])[0]
            state = job_info.get("job_state", "UNKNOWN")
            if verbose:
                print(f"Job {jobid} status: {state}")

            if state in ["COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"]:
                if verbose:
                    print(f"Job {jobid} has finished with state: {state}")
                break
        else:
            print(f"Error: {response.status_code}, {response.text}")
            break

        time.sleep(5)  # Poll every 5 seconds

    return state


p = argparse.ArgumentParser(description="tiny rest submit tool")
p.add_argument("-v", "--verbose",
               action="store_true",
               help="Enable verbose output.")
p.add_argument("-w", "--wait",
               action="store_true",
               help="Wait (poll) on job to complete.")
args = p.parse_args()

SLURM_API_BASE_URL = "http://localhost:6820/slurm/v0.0.39"

if 'SLURM_JWT' in os.environ:
    MY_TOKEN = os.environ.get('SLURM_JWT')
    if args.verbose:
        print(f"FOUND TOKEN IN ENV:\n {MY_TOKEN}")
else:
    MY_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NDI5MzYzOTMsImlhdCI6MTc0MjkzNDU5Mywic3VuIjoic2dydW5keSJ9.HFZd56WeYMvX4jrx3D9OADo2TV24EOdIBFzZYNkXe2w"
    if args.verbose:
        print(f"TRY A DEFAULT TOKEN:\n {MY_TOKEN}")


HEADERS = {
        "Content-type": "application/json",
        "X-SLURM-USER-NAME": "sgrundy",
        "X-SLURM-USER-TOKEN": MY_TOKEN,
}

#                "hostname; date ; sleep 5 ; date; "
#                "echo \"Goodbye.\"; ",
payload = {
    "job": {
      "script": "#!/bin/bash --login\n echo \"testing api ${HELLO}\" ",
      "name": "DummyJob",
      "current_working_directory": "/home/sgrundy",
      "environment": [
        "HELLO=world"
      ],
      "nodes": "1",
      "tasks": 1,
      "time_limit": 10,
    }
}

#payload = json.dumps(job_script)

url_submit = SLURM_API_BASE_URL + "/job/submit"
# Submit the job
response = requests.post(url_submit, headers=HEADERS, json=payload)

if response.status_code == 200:
    print("Job submitted successfully!")
    if args.verbose:
        print(json.dumps(response.json(), indent=4))
    data = response.json()
    jid = data['job_id']
    jstat = data['result']['error_code']

    print(f"INFO: Job_ID: {jid}  Error_code: {jstat}  Response_Code: {response.status_code}")

    url_jobinfo = SLURM_API_BASE_URL + f"/job/{jid}"

    state = poll_job_status(url_jobinfo, HEADERS, jid, verbose=args.verbose)
    print(f"Job_ID: {jid} FinishStatus: {state}")

else:
    print(f"Failed to submit job: {response.status_code} {response.text}")

print("Done")
