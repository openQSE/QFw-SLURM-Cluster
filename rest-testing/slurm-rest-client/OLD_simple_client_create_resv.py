import os
import sys
import json
import datetime
import calendar

from slurmrest_client.openapi_client.configuration import Configuration
from slurmrest_client.openapi_client.api_client import ApiClient
from slurmrest_client.openapi_client.exceptions import ApiException
from slurmrest_client.openapi_client.api.slurm_api import SlurmApi

from slurmrest_client.openapi_client.models.v0043_reservation_desc_msg import V0043ReservationDescMsg


from slurmrest_client.openapi_client.models.v0043_uint32_no_val_struct import V0043Uint32NoValStruct
from slurmrest_client.openapi_client.models.v0043_uint64_no_val_struct import V0043Uint64NoValStruct

def wrap_uint32(val: int) -> V0043Uint32NoValStruct:
    return V0043Uint32NoValStruct(number=val, set=True, infinite=False)

def wrap_uint64(val: int) -> V0043Uint64NoValStruct:
    return V0043Uint64NoValStruct(number=val, set=True, infinite=False)


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
        # Step 3: Call the function to create a reservation
#            nodes="c[1]",
#            flags=[ReservationFlag.MAINT]


        dt = datetime.datetime.fromisoformat("2025-07-24T12:00:00+00:00")
        start_timestamp = calendar.timegm(dt.timetuple())

#        reservation_req = V0043ReservationDescMsg(
#            name="mytestresv123",
#            #users=["sgrundy"],
#            #node_count=wrap_uint32(1),
#            #duration=wrap_uint32(3600),
#            #start_time=wrap_uint64(start_timestamp)
#        )

        resv_desc_msg = V0043ReservationDescMsg(
            name="mytestresv666",
            start_time=wrap_uint64(start_timestamp),
            duration=wrap_uint32(3600),
            users=["sgrundy"],
            node_count=wrap_uint32(1)
        )

#duration
#  Input should be a valid dictionary or instance of V0043Uint32NoValStruct [type=model_type, input_value=V0043Uint32NoValStruct(se...nite=False, number=3600), input_type=V0043Uint32NoValStruct]
#    For further information visit https://errors.pydantic.dev/2.11/v/model_type
#node_count
#  Input should be a valid dictionary or instance of V0043Uint32NoValStruct [type=model_type, input_value=V0043Uint32NoValStruct(se...nfinite=False, number=1), input_type=V0043Uint32NoValStruct]
#    For further information visit https://errors.pydantic.dev/2.11/v/model_type
#start_time
#  Input should be a valid dictionary or instance of V0043Uint64NoValStruct [type=model_type, input_value=V0043Uint64NoValStruct(se...alse, number=1753358400), input_type=V0043Uint64NoValStruct]
#    For further information visit https://errors.pydantic.dev/2.11/v/model_type

        reservation = api_instance.slurm_v0043_post_reservation(v0043_reservation_desc_msg=resv_desc_msg)
        print(f"Created reservation: {reservation}")

#        api_instance.slurm_v0043_post_reservation(resv_desc_msg)
#        reservation = api_instance.slurm_v0043_post_reservation()

    except ApiException as e:
        print("Exception when calling slurm_v0043_post_reservation: %s\n" % e)

