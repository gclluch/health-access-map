import { scaleSequential, scaleQuantile } from 'd3-scale';
import { interpolateCividis } from 'd3-scale-chromatic';

// Cividis: perceptually-uniform AND optimized for color-vision deficiency
// (§14.2). Rainbow/jet are forbidden -- they imply false thresholds.
// Direction: 0 -> low (sand), 100 -> high (oxblood/dark). For the access gap,
// higher = worse, which reads as darker = more gap. Good.
export const RAMP = (t: number) => interpolateCividis(t);

export const NO_DATA_RGB: [number, number, number] = [202, 206, 212]; // hairline-gray
export const SELECTED_OUTLINE: [number, number, number, number] = [20, 84, 90, 255]; // petrol

const seq = scaleSequential(interpolateCividis).domain([0, 100]);

// d3 interpolators may return "rgb(r, g, b)" or "#rrggbb"; handle both.
function parseColor(c: string): [number, number, number] {
  const rgb = c.match(/rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
  if (rgb) return [+rgb[1], +rgb[2], +rgb[3]];
  const m = c.replace('#', '');
  return [
    parseInt(m.slice(0, 2), 16),
    parseInt(m.slice(2, 4), 16),
    parseInt(m.slice(4, 6), 16),
  ];
}

// Quantile binning is honest for skewed data (§14.2). We build the scale from the
// actual value domain each time the active metric changes.
export function buildQuantile(values: number[]) {
  const scale = scaleQuantile<string>()
    .domain(values)
    .range(['0', '0.14', '0.28', '0.42', '0.56', '0.7', '0.85', '1'].map((s) => seq(+s * 100)));
  return scale;
}

export function colorFor(value: number | null, scale: ReturnType<typeof buildQuantile>): [number, number, number] {
  if (value == null || Number.isNaN(value)) return NO_DATA_RGB;
  return parseColor(scale(value));
}

// Legend break values for the active domain.
export function quantileBreaks(scale: ReturnType<typeof buildQuantile>): number[] {
  return scale.quantiles();
}
