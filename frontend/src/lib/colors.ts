import { scaleSequential, scaleQuantile } from 'd3-scale';
import { interpolateCividis } from 'd3-scale-chromatic';

// Cividis: perceptually-uniform AND optimized for color-vision deficiency
// (§14.2). Rainbow/jet are forbidden -- they imply false thresholds.
// Direction: 0 -> deep blue (low), 100 -> bright yellow (high). For access disadvantage,
// higher = worse, so BRIGHTER YELLOW = more disadvantage and DEEP BLUE = less.
export const RAMP = (t: number) => interpolateCividis(t);

export const NO_DATA_RGB: [number, number, number] = [202, 206, 212]; // hairline-gray
export const SELECTED_OUTLINE: [number, number, number, number] = [20, 84, 90, 255]; // petrol
// Selection halo: a near-black casing under a white line reads clearly against BOTH
// ends of the ramp (deep blue and bright yellow). Used as a dedicated overlay layer.
export const SELECT_CASING: [number, number, number, number] = [16, 20, 27, 235]; // ink
export const SELECT_LINE: [number, number, number, number] = [255, 255, 255, 255]; // white

// Chrome colors for canvas/SVG contexts (deck.gl layers, inline <svg>, the HTML
// tooltip) that cannot use Tailwind classes. Single source so they stay in lockstep
// with tailwind.config.js instead of being re-typed as raw hex at each call site.
export const CHROME = {
  ink: '#14181F',         // tooltip background (== tailwind `ink`)
  accent: '#14545A',      // selected histogram bar + marker (== tailwind `accent`)
  histBar: '#9AA4B2',     // unselected histogram bars
  tooltipMono: '#C9CDD6', // muted mono text on the dark tooltip
} as const;
export const HOVER_LINE: [number, number, number, number] = [20, 84, 90, 220]; // accent, hovered border
export const IDLE_LINE: [number, number, number, number] = [120, 130, 145, 40]; // quiet idle border

const seq = scaleSequential(interpolateCividis).domain([0, 100]);
export const QUANTILE_STOPS = [0, 0.14, 0.28, 0.42, 0.56, 0.7, 0.85, 1] as const;
export const QUANTILE_COLORS = QUANTILE_STOPS.map((s) => seq(s * 100));

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
    .range(QUANTILE_COLORS);
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
