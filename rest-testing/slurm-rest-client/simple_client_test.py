import os
import sys
import json

#from slurmrest_client import Configuration, ApiClient
#from slurmrest_client.api.slurm_v0043_api import SlurmV0043Api
#from slurmrest_client.exceptions import ApiException
from slurmrest_client.openapi_client.configuration import Configuration
from slurmrest_client.openapi_client.api_client import ApiClient
from slurmrest_client.openapi_client.exceptions import ApiException
#from slurmrest_client.openapi_client.api.slurm_v0043_api import SlurmV0043Api
from slurmrest_client.openapi_client.api.slurm_api import SlurmApi


#----
## Debug HTTP requests
# import logging
# import http.client as http_client
#
# http_client.HTTPConnection.debuglevel = 1
# logging.basicConfig()
# logging.getLogger().setLevel(logging.DEBUG)
#----


TOKEN = os.getenv("SLURM_JWT")
if not TOKEN:
    raise ValueError("ERROR: SLURM_JWT is not set in env")

# Step 1: Configure client
configuration = Configuration()
configuration.host = "http://localhost:6820"
configuration.api_key = {
    'X-SLURM-USER-TOKEN': TOKEN
}
configuration.api_key_prefix = {
    'X-SLURM-USER-TOKEN': ""}  # No "Bearer", just raw token


#print(f"DBG: API_KEY={configuration.api_key}")
#print(f"DBG: API_KEY_PREFIX={configuration.api_key_prefix}")

# Optional: if not using token, may need to set username too
# configuration.api_key['X-SLURM-USER-NAME'] = 'your_username'

# Step 2: Instantiate API client
with ApiClient(configuration) as api_client:
    #api_instance = SlurmV0043Api(api_client)

    #####
    # TJN: I have a problem with the default API headers
    #      but can not figure out what is causing issue
    #      so just clobbering them and setting our token manually!
    #      This should *not* be needed with above configuration.api_key,
    #      but life is not fair.  Moving on. :-/
    api_client.default_headers["X-SLURM-USER-TOKEN"] = TOKEN # XXX: CLOBBER headers
    #####

    api_instance = SlurmApi(api_client)

    try:
        # Step 3: Call the function to get reservations
        result = api_instance.slurm_v0043_get_reservations()
        for r in result.reservations:
            print(f"Reservation: {r.name}, Nodes: {r.node_list}, Node_Count: {r.node_count}, Start: {r.start_time}")
            # r.partition
            # r.users

    except ApiException as e:
        print("Exception when calling slurm_v0043_get_reservation: %s\n" % e)

