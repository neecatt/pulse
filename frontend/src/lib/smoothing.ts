/**
 * Exponential moving average with debiasing, as TensorBoard does it: early
 * values aren't pulled towards zero. ``weight`` is 0 (off) to just below 1.
 */
export function smooth(values: number[], weight: number): number[] {
  if (weight <= 0) return values;
  let average = 0;
  let correction = 0;
  return values.map((value) => {
    average = average * weight + (1 - weight) * value;
    correction = correction * weight + (1 - weight);
    return average / correction;
  });
}
