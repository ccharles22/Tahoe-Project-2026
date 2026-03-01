# Distribution plot

The activity score distribution view shows how performance changes across
generations, making it easier to interpret whether the experiment is broadly
improving, becoming more variable, or producing isolated high-performing
outliers.

## Data sources

- Activity scores: `metrics` where `metric_name='activity_score'` and
  `metric_type='derived'`
- Variant and generation metadata: `variants`, `generations`

## Endpoint

`/distribution/<experiment_id>`

Example:

`/distribution/41`

## Validation check

To validate this plot, check that the experiment has derived `activity_score`
rows across multiple generations. The distribution chart groups those stored
scores by generation number and then renders one violin per generation.

## Interpretation

- Each violin summarizes the full distribution of activity scores for one
  generation.
- The red baseline at `1.0` represents neutral normalized activity.
- Shifts upward in the center of the violins suggest improved performance across
  the population.
- Wider shapes indicate more dispersion, which can reflect broader exploration
  of sequence space or unstable selection.
- Strong outliers can indicate the emergence of highly successful variants even
  when the generation-wide median changes only slightly.

This plot is most useful when interpreted alongside Top 10 and Lineage, because
it shows whether top performers reflect a broad generation-wide trend or only a
small exceptional subgroup.

## Example graph

![Distribution example](assets/plots/distribution_exp41.png)
