# V0042JobResNodeMemory


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**used** | **int** | Total memory (MiB) used by job | [optional] 
**allocated** | **int** | Total memory (MiB) allocated to job | [optional] 

## Example

```python
from openapi_client.models.v0042_job_res_node_memory import V0042JobResNodeMemory

# TODO update the JSON string below
json = "{}"
# create an instance of V0042JobResNodeMemory from a JSON string
v0042_job_res_node_memory_instance = V0042JobResNodeMemory.from_json(json)
# print the JSON string representation of the object
print(V0042JobResNodeMemory.to_json())

# convert the object into a dict
v0042_job_res_node_memory_dict = v0042_job_res_node_memory_instance.to_dict()
# create an instance of V0042JobResNodeMemory from a dict
v0042_job_res_node_memory_from_dict = V0042JobResNodeMemory.from_dict(v0042_job_res_node_memory_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


