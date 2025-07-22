# V0042PartitionInfoCpus


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**task_binding** | **int** | CpuBind | [optional] 
**total** | **int** | TotalCPUs | [optional] 

## Example

```python
from openapi_client.models.v0042_partition_info_cpus import V0042PartitionInfoCpus

# TODO update the JSON string below
json = "{}"
# create an instance of V0042PartitionInfoCpus from a JSON string
v0042_partition_info_cpus_instance = V0042PartitionInfoCpus.from_json(json)
# print the JSON string representation of the object
print(V0042PartitionInfoCpus.to_json())

# convert the object into a dict
v0042_partition_info_cpus_dict = v0042_partition_info_cpus_instance.to_dict()
# create an instance of V0042PartitionInfoCpus from a dict
v0042_partition_info_cpus_from_dict = V0042PartitionInfoCpus.from_dict(v0042_partition_info_cpus_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


