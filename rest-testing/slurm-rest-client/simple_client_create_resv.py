import os
import datetime
import calendar

from slurmrest_client.openapi_client.configuration import Configuration
from slurmrest_client.openapi_client.api_client import ApiClient
from slurmrest_client.openapi_client.api.slurm_api import SlurmApi
from slurmrest_client.openapi_client.models.v0043_reservation_desc_msg import V0043ReservationDescMsg
from slurmrest_client.openapi_client.models.v0043_uint32_no_val_struct import V0043Uint32NoValStruct
from slurmrest_client.openapi_client.models.v0043_uint64_no_val_struct import V0043Uint64NoValStruct

# Correct wrapper functions: use 'infinite' field, not 'finite'
def wrap_uint32(val: int) -> V0043Uint32NoValStruct:
    return {"infinite": False, "number": val}
#    return V0043Uint32NoValStruct(infinite=False, number=val)

def wrap_uint64(val: int) -> V0043Uint64NoValStruct:
    return {"infinite": False, "number": val}
#    return V0043Uint64NoValStruct(infinite=False, number=val)


def main():
    #
    # Reminder:
    #   laptop:$ scontrol token
    #   SLURM_JWT=xxxxxx...
    #   laptop:$ export SLURM_JWT=xxxxxx...
    #
    TOKEN = os.getenv("SLURM_JWT")
    if not TOKEN:
        raise ValueError("ERROR: SLURM_JWT is not set in environment variables")

    # Setup client config
    configuration = Configuration()
    configuration.host = "http://localhost:6820"
    configuration.api_key = {'X-SLURM-USER-TOKEN': TOKEN}
    configuration.api_key_prefix = {'X-SLURM-USER-TOKEN': ""}  # No Bearer prefix

    with ApiClient(configuration) as api_client:
        # Force token header in case of client issues
        api_client.default_headers["X-SLURM-USER-TOKEN"] = TOKEN

        #####
        # TJN: I have a problem with the default API headers
        #      but can not figure out what is causing issue
        #      so just clobbering them and setting our token manually!
        #      This should *not* be needed with above configuration.api_key,
        #      but life is not fair.  Moving on. :-/
        api_client.default_headers["X-SLURM-USER-TOKEN"] = TOKEN # XXX: CLOBBER headers
        #####

        api_instance = SlurmApi(api_client)

        # Prepare timestamp for reservation start time
        dt = datetime.datetime.fromisoformat("2025-07-24T12:00:01+00:00")
        start_timestamp = calendar.timegm(dt.utctimetuple())

#        # Create reservation description with correct wrapped types
#        resv_desc_msg = V0043ReservationDescMsg(
#            name="mytestresv",
#            start_time=wrap_uint64(start_timestamp),
#            duration=wrap_uint32(3600),     # 1 hour
#            node_count=wrap_uint32(1),
#            users=["sgrundy"],          # Replace with your actual username
#        )
        resv_desc_msg = V0043ReservationDescMsg(
            name="mytestresv",
            start_time={"set": True, "infinite": False, "number": start_timestamp},
            duration={"set": True, "infinite": False, "number": 3600},
            node_count={"set": True, "infinite": False, "number": 1},
            users=["sgrundy"],
        )



        try:
            print(resv_desc_msg.model_dump_json(indent=2))
            #reservation = api_instance.slurm_v0043_post_reservation(v0043_reservation_desc_msg=resv_desc_msg)
            # Pass dict, not model instance
            reservation = api_instance.slurm_v0043_post_reservation(
                v0043_reservation_desc_msg=resv_desc_msg.dict(exclude_none=True)
            )
            print(f"Reservation created: {reservation}")
        except Exception as e:
            print(f"Exception when creating reservation: {e}")

if __name__ == "__main__":
    main()

