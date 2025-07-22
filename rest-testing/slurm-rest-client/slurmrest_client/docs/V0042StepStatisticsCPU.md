# V0042StepStatisticsCPU


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**actual_frequency** | **int** | Average weighted CPU frequency of all tasks in kHz | [optional] 

## Example

```python
from openapi_client.models.v0042_step_statistics_cpu import V0042StepStatisticsCPU

# TODO update the JSON string below
json = "{}"
# create an instance of V0042StepStatisticsCPU from a JSON string
v0042_step_statistics_cpu_instance = V0042StepStatisticsCPU.from_json(json)
# print the JSON string representation of the object
print(V0042StepStatisticsCPU.to_json())

# convert the object into a dict
v0042_step_statistics_cpu_dict = v0042_step_statistics_cpu_instance.to_dict()
# create an instance of V0042StepStatisticsCPU from a dict
v0042_step_statistics_cpu_from_dict = V0042StepStatisticsCPU.from_dict(v0042_step_statistics_cpu_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


