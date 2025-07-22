# V0042JobResNodeCpus


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**count** | **int** | Total number of CPUs assigned to job | [optional] 
**used** | **int** | Total number of CPUs used by job | [optional] 

## Example

```python
from openapi_client.models.v0042_job_res_node_cpus import V0042JobResNodeCpus

# TODO update the JSON string below
json = "{}"
# create an instance of V0042JobResNodeCpus from a JSON string
v0042_job_res_node_cpus_instance = V0042JobResNodeCpus.from_json(json)
# print the JSON string representation of the object
print(V0042JobResNodeCpus.to_json())

# convert the object into a dict
v0042_job_res_node_cpus_dict = v0042_job_res_node_cpus_instance.to_dict()
# create an instance of V0042JobResNodeCpus from a dict
v0042_job_res_node_cpus_from_dict = V0042JobResNodeCpus.from_dict(v0042_job_res_node_cpus_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


