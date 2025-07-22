# V0042StepTimeUser


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**seconds** | **int** | User CPU time used by the step in seconds | [optional] 
**microseconds** | **int** | User CPU time used by the step in microseconds | [optional] 

## Example

```python
from openapi_client.models.v0042_step_time_user import V0042StepTimeUser

# TODO update the JSON string below
json = "{}"
# create an instance of V0042StepTimeUser from a JSON string
v0042_step_time_user_instance = V0042StepTimeUser.from_json(json)
# print the JSON string representation of the object
print(V0042StepTimeUser.to_json())

# convert the object into a dict
v0042_step_time_user_dict = v0042_step_time_user_instance.to_dict()
# create an instance of V0042StepTimeUser from a dict
v0042_step_time_user_from_dict = V0042StepTimeUser.from_dict(v0042_step_time_user_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


