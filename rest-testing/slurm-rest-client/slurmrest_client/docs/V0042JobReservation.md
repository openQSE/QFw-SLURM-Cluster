# V0042JobReservation


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **int** | Unique identifier of requested reservation | [optional] 
**name** | **str** | Name of reservation to use | [optional] 

## Example

```python
from openapi_client.models.v0042_job_reservation import V0042JobReservation

# TODO update the JSON string below
json = "{}"
# create an instance of V0042JobReservation from a JSON string
v0042_job_reservation_instance = V0042JobReservation.from_json(json)
# print the JSON string representation of the object
print(V0042JobReservation.to_json())

# convert the object into a dict
v0042_job_reservation_dict = v0042_job_reservation_instance.to_dict()
# create an instance of V0042JobReservation from a dict
v0042_job_reservation_from_dict = V0042JobReservation.from_dict(v0042_job_reservation_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


