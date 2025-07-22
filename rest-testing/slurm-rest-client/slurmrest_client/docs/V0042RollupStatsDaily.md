# V0042RollupStatsDaily


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**count** | **int** | Number of daily rollups since last_run | [optional] 
**last_run** | **int** | Last time daily rollup ran (UNIX timestamp) | [optional] 
**duration** | [**V0042RollupStatsDailyDuration**](V0042RollupStatsDailyDuration.md) |  | [optional] 

## Example

```python
from openapi_client.models.v0042_rollup_stats_daily import V0042RollupStatsDaily

# TODO update the JSON string below
json = "{}"
# create an instance of V0042RollupStatsDaily from a JSON string
v0042_rollup_stats_daily_instance = V0042RollupStatsDaily.from_json(json)
# print the JSON string representation of the object
print(V0042RollupStatsDaily.to_json())

# convert the object into a dict
v0042_rollup_stats_daily_dict = v0042_rollup_stats_daily_instance.to_dict()
# create an instance of V0042RollupStatsDaily from a dict
v0042_rollup_stats_daily_from_dict = V0042RollupStatsDaily.from_dict(v0042_rollup_stats_daily_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


