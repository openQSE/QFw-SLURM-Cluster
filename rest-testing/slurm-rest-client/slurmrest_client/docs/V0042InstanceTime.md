# V0042InstanceTime


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**time_end** | **int** | When the instance will end (UNIX timestamp) | [optional] 
**time_start** | **int** | When the instance will start (UNIX timestamp) | [optional] 

## Example

```python
from openapi_client.models.v0042_instance_time import V0042InstanceTime

# TODO update the JSON string below
json = "{}"
# create an instance of V0042InstanceTime from a JSON string
v0042_instance_time_instance = V0042InstanceTime.from_json(json)
# print the JSON string representation of the object
print(V0042InstanceTime.to_json())

# convert the object into a dict
v0042_instance_time_dict = v0042_instance_time_instance.to_dict()
# create an instance of V0042InstanceTime from a dict
v0042_instance_time_from_dict = V0042InstanceTime.from_dict(v0042_instance_time_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


