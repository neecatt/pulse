/** Index of the x closest to `target` in sorted `xs` (binary search). */
export function nearestIndex(xs: number[], target: number): number | null {
  if (xs.length === 0) return null;
  let lo = 0;
  let hi = xs.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if ((xs[mid] ?? 0) < target) lo = mid + 1;
    else hi = mid;
  }
  const prev = lo - 1;
  if (prev >= 0 && Math.abs((xs[prev] ?? 0) - target) <= Math.abs((xs[lo] ?? 0) - target)) {
    return prev;
  }
  return lo;
}
