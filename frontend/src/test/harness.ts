import { useStore } from '../store';
import { DEFAULT_WEIGHTS, type SlimMetric } from '../lib/types';

// A fully-populated SlimMetric so a spec only states the fields it is actually about. Defaults
// describe an ordinary scoreable residential ZIP: everything a caveat or an exclusion keys off
// (low_confidence, institutional, scoreable, n_dims_scored) is in its benign state.
export function makeMetric(over: Partial<SlimMetric> & { zcta5: string }): SlimMetric {
  const pctiles = [
    'life_expectancy_pctile', 'health_need_pctile', 'social_vulnerability_pctile',
    'care_access_pctile', 'care_access_resid_pctile', 'chronic_disease_pctile',
    'behavioral_risk_pctile', 'mental_social_health_pctile', 'disability_pctile',
    'socioeconomic_pctile', 'housing_transport_pctile', 'social_needs_pctile',
    'digital_access_pctile', 'provider_supply_pctile', 'shortage_designation_pctile',
    'safetynet_access_pctile', 'insurance_pctile', 'medical_debt_pctile', 'preventive_use_pctile',
  ] as const;
  const base = {
    state: 'CA', state_name: 'California', city: 'Somewhere', county_name: 'Some County',
    population: 25000, life_expectancy: 78,
    access_gap_score: 50, access_gap_pctile: 50, access_gap_pctile_within_state: 50,
    access_gap_rank_lo: 45, access_gap_rank_hi: 55, tier: 5,
    low_confidence: false, institutional: false, scoreable: true, n_dims_scored: 3,
  };
  for (const p of pctiles) (base as Record<string, unknown>)[p] = 50;
  return { ...(base as unknown as SlimMetric), ...over };
}

// The store is a module singleton, so every spec must put it back or ordering decides the result.
export function seedStore(metrics: SlimMetric[], over: Partial<ReturnType<typeof useStore.getState>> = {}) {
  useStore.setState({
    metrics: new Map(metrics.map((m) => [m.zcta5, m])),
    weights: { ...DEFAULT_WEIGHTS },
    selectedZcta: null,
    hoveredZcta: null,
    compareZctas: [],
    stateFilter: null,
    rankOrder: 'desc',
    showMethodology: false,
    subscoresStatus: 'ready',
    ...over,
  });
}
