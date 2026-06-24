// Slim metric record from join_and_score (_write_slim_json): geography + the
// composite + 3 dimension percentiles + 11 sub-score percentiles + flags. Raw
// measures are fetched per-ZIP from the API for the drill-down.
export interface SlimMetric {
  zcta5: string;
  state: string | null;
  state_name: string | null;
  city: string | null;
  county_name: string | null;
  population: number | null;
  life_expectancy: number | null;
  life_expectancy_pctile: number | null;
  access_gap_score: number | null;
  access_gap_pctile: number | null;
  access_gap_rank_lo: number | null;  // 5-95 national-rank band under plausible re-weighting
  access_gap_rank_hi: number | null;
  tier: number | null;                // decile 1-10 (the resolution the data supports)
  low_confidence: boolean;
  scoreable: boolean;
  // dimensions
  health_need_pctile: number | null;
  social_vulnerability_pctile: number | null;
  care_access_pctile: number | null;
  // sub-scores
  chronic_disease_pctile: number | null;
  behavioral_risk_pctile: number | null;
  mental_social_health_pctile: number | null;
  disability_pctile: number | null;
  socioeconomic_pctile: number | null;
  housing_transport_pctile: number | null;
  social_needs_pctile: number | null;
  digital_access_pctile: number | null;
  provider_supply_pctile: number | null;
  shortage_designation_pctile: number | null;
  safetynet_access_pctile: number | null;
  insurance_pctile: number | null;
  preventive_use_pctile: number | null;
  [k: string]: string | number | boolean | null;
}

export const STATE_NAMES: Record<string, string> = {
  AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California',
  CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware', DC: 'District of Columbia',
  FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois',
  IN: 'Indiana', IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana',
  ME: 'Maine', MD: 'Maryland', MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota',
  MS: 'Mississippi', MO: 'Missouri', MT: 'Montana', NE: 'Nebraska', NV: 'Nevada',
  NH: 'New Hampshire', NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York',
  NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio', OK: 'Oklahoma', OR: 'Oregon',
  PA: 'Pennsylvania', PR: 'Puerto Rico', RI: 'Rhode Island', SC: 'South Carolina',
  SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VT: 'Vermont',
  VA: 'Virginia', WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming',
};

export type DimKey = 'health_need' | 'social_vulnerability' | 'care_access';

export interface Weights {
  health_need: number;
  social_vulnerability: number;
  care_access: number;
}

export const DEFAULT_WEIGHTS: Weights = {
  health_need: 35,
  social_vulnerability: 30,
  care_access: 35,
};

export const PRESETS: Record<string, Weights> = {
  Balanced: { health_need: 35, social_vulnerability: 30, care_access: 35 },
  'Need-focused': { health_need: 55, social_vulnerability: 30, care_access: 15 },
  'Access-focused': { health_need: 20, social_vulnerability: 25, care_access: 55 },
  'Vulnerability-focused': { health_need: 25, social_vulnerability: 50, care_access: 25 },
};

// Outcome-anchored validation, produced by pipeline/validate.py -> weights.json. Each
// anchor is an independent (non-PLACES) outcome; `weights` are correlation-based presets
// (care access stays visible), `regressionWeights` is the NNLS diagnostic that collapses
// it via collinearity. See docs/VALIDATION.md.
export interface AnchorPreset {
  key: string;
  label: string;
  scope: string;
  caveat: string;
  weights: Weights;
  regressionWeights: Weights | null;
  fit: { r2: number; n: number } | null;
  dimensionCorr: Partial<Record<DimKey, number | null>>;
}
// anchor key -> sub-score key -> signed correlation
export type SubscoreCorrelations = Record<string, Record<string, number>>;

interface RawAnchor {
  label: string; scope: string; caveat: string; weights: Weights;
  regression_weights: Weights | null; fit: { r2: number; n: number } | null;
  dimension_corr: Partial<Record<DimKey, number | null>>;
}
interface RawWeights {
  default: Weights;
  anchors?: Record<string, RawAnchor>;
  subscore_correlations?: SubscoreCorrelations;
}

export function parseAnchors(raw: RawWeights): AnchorPreset[] {
  return Object.entries(raw.anchors ?? {}).map(([key, a]) => ({
    key, label: a.label, scope: a.scope, caveat: a.caveat, weights: a.weights,
    regressionWeights: a.regression_weights, fit: a.fit, dimensionCorr: a.dimension_corr,
  }));
}

// The hierarchy, mirroring pipeline/taxonomy.py — drives the Color-by menu,
// the drill-down panel, and the rankings selector.
export interface SubSpec { key: string; label: string; scored?: boolean }
export interface DimSpec { key: DimKey; label: string; blurb: string; subs: SubSpec[] }

export const MODEL: DimSpec[] = [
  {
    key: 'health_need',
    label: 'Health need',
    blurb: 'Chronic disease, behavioral risk, mental/social health, disability.',
    subs: [
      { key: 'chronic_disease', label: 'Chronic disease' },
      { key: 'behavioral_risk', label: 'Behavioral risk' },
      { key: 'mental_social_health', label: 'Mental & social distress' },
      { key: 'disability', label: 'Disability' },
    ],
  },
  {
    key: 'social_vulnerability',
    label: 'Social vulnerability',
    blurb: 'Socioeconomic deprivation, housing/transport barriers, unmet social needs, and digital/telehealth access.',
    subs: [
      { key: 'socioeconomic', label: 'Socioeconomic deprivation' },
      { key: 'housing_transport', label: 'Housing & transport barriers' },
      { key: 'social_needs', label: 'Unmet social needs' },
      { key: 'digital_access', label: 'Digital / telehealth access' },
    ],
  },
  {
    key: 'care_access',
    label: 'Barriers to care',
    blurb: 'Low provider supply, official provider shortage (HPSA), and lack of insurance. Higher = more barriers. (Two items are shown for context but NOT scored: safety-net need, wrong-signed within counties; and preventive-care use, which is realized utilization - an outcome of access, not a barrier. See methodology.)',
    subs: [
      { key: 'provider_supply', label: 'Low provider supply (spatial)' },
      { key: 'shortage_designation', label: 'Official provider shortage (HPSA)' },
      { key: 'safetynet_access', label: 'Unmet safety-net need (FQHC desert)', scored: false },
      { key: 'insurance', label: 'Lack of insurance' },
      { key: 'preventive_use', label: 'Low preventive-care use (realized access)', scored: false },
    ],
  },
];

// Any colorable / rankable metric column = the composite, a dimension, a sub-score,
// or an outcome (life expectancy, which is NOT in the composite — outcomes are the
// result, not a driver; kept separate à la County Health Rankings).
export const COMPOSITE_METRIC = 'access_gap_score';
// The multiplicative "coincidence" lens: weighted GEOMETRIC mean of the 3 dimensions
// (OECD non-compensatory aggregation). Lights up only where need AND barriers coincide,
// vs the additive default which is fully compensatory. Recomputed client-side from the
// dimension percentiles (respects the weight sliders), same 0-100 scale as the composite.
export const COMPOSITE_MULT_METRIC = 'access_gap_mult';

export const OUTCOME_METRICS: SubSpec[] = [
  { key: 'life_expectancy', label: 'Low life expectancy' }, // colors by life_expectancy_pctile
];

export function metricLabel(metric: string): string {
  if (metric === COMPOSITE_METRIC) return 'Access gap';
  if (metric === COMPOSITE_MULT_METRIC) return 'Access gap (coincidence lens)';
  const base = metric.replace(/_pctile$/, '');
  for (const d of MODEL) {
    if (d.key === base) return d.label;
    const s = d.subs.find((x) => x.key === base);
    if (s) return s.label;
  }
  const o = OUTCOME_METRICS.find((x) => x.key === base);
  if (o) return o.label;
  return metric;
}

export const ALL_METRICS: string[] = [
  COMPOSITE_METRIC,
  ...MODEL.map((d) => `${d.key}_pctile`),
  ...MODEL.flatMap((d) => d.subs.map((s) => `${s.key}_pctile`)),
  ...OUTCOME_METRICS.map((o) => `${o.key}_pctile`),
];
