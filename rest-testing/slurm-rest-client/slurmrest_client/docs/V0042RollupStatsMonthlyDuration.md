# V0042RollupStatsMonthlyDuration


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**last** | **int** | Total time spent doing monthly daily rollup (seconds) | [optional] 
**max** | **int** | Longest monthly rollup time (seconds) | [optional] 
**time** | **int** | Total time spent doing monthly rollups (seconds) | [optional] 

## Example

```python
from openapi_client.models.v0042_rollup_stats_monthly_duration import V0042RollupStatsMonthlyDuration

# TODO update the JSON string below
json = "{}"
# create an instance of V0042RollupStatsMonthlyDuration from a JSON string
v0042_rollup_stats_monthly_duration_instance = V0042RollupStatsMonthlyDuration.from_json(json)
# print the JSON string representation of the object
print(V0042RollupStatsMonthlyDuration.to_json())

# convert the object into a dict
v0042_rollup_stats_monthly_duration_dict = v0042_rollup_stats_monthly_duration_instance.to_dict()
# create an instance of V0042RollupStatsMonthlyDuration from a dict
v0042_rollup_stats_monthly_duration_from_dict = V0042RollupStatsMonthlyDuration.from_dict(v0042_rollup_stats_monthly_duration_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


