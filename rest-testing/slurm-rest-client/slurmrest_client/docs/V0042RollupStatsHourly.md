# V0042RollupStatsHourly


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**count** | **int** | Number of hourly rollups since last_run | [optional] 
**last_run** | **int** | Last time hourly rollup ran (UNIX timestamp) | [optional] 
**duration** | [**V0042RollupStatsHourlyDuration**](V0042RollupStatsHourlyDuration.md) |  | [optional] 

## Example

```python
from openapi_client.models.v0042_rollup_stats_hourly import V0042RollupStatsHourly

# TODO update the JSON string below
json = "{}"
# create an instance of V0042RollupStatsHourly from a JSON string
v0042_rollup_stats_hourly_instance = V0042RollupStatsHourly.from_json(json)
# print the JSON string representation of the object
print(V0042RollupStatsHourly.to_json())

# convert the object into a dict
v0042_rollup_stats_hourly_dict = v0042_rollup_stats_hourly_instance.to_dict()
# create an instance of V0042RollupStatsHourly from a dict
v0042_rollup_stats_hourly_from_dict = V0042RollupStatsHourly.from_dict(v0042_rollup_stats_hourly_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


