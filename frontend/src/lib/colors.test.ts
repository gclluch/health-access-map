import { describe, it, expect } from 'vitest';
import { buildQuantile, colorFor, quantileBreaks, NO_DATA_RGB } from './colors';

describe('quantile color scale', () => {
  const values = Array.from({ length: 100 }, (_, i) => i); // 0..99
  const scale = buildQuantile(values);

  it('maps a value to an [r,g,b] triple', () => {
    const c = colorFor(50, scale);
    expect(c).toHaveLength(3);
    c.forEach((ch) => expect(ch).toBeGreaterThanOrEqual(0));
    c.forEach((ch) => expect(ch).toBeLessThanOrEqual(255));
  });

  it('returns the no-data gray for null/NaN', () => {
    expect(colorFor(null, scale)).toEqual(NO_DATA_RGB);
    expect(colorFor(NaN, scale)).toEqual(NO_DATA_RGB);
  });

  it('is monotonic: high values are brighter (higher channel sum) than low values', () => {
    const lo = colorFor(2, scale).reduce((a, b) => a + b, 0);
    const hi = colorFor(98, scale).reduce((a, b) => a + b, 0);
    expect(hi).toBeGreaterThan(lo); // cividis brightens toward the high (worse) end
  });

  it('exposes 7 internal breaks for an 8-bin ramp', () => {
    expect(quantileBreaks(scale)).toHaveLength(7);
  });
});
