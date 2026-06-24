import type { SlimMetric } from './types';

// Minimal SlimMetric builder for unit tests: every required field defaulted, override
// the few that a test cares about. Kept out of *.test.ts so vitest doesn't treat it as a suite.
export function makeMetric(over: Partial<SlimMetric> = {}): SlimMetric {
  return {
    zcta5: '00000',
    state: 'CA',
    state_name: 'California',
    city: 'Testville',
    county_name: 'Test County',
    population: 10000,
    life_expectancy: null,
    life_expectancy_pctile: null,
    access_gap_score: null,
    access_gap_pctile: null,
    access_gap_rank_lo: null,
    access_gap_rank_hi: null,
    care_access_resid_pctile: null,
    tier: null,
    low_confidence: false,
    scoreable: true,
    n_dims_scored: 3,
    health_need_pctile: 50,
    social_vulnerability_pctile: 50,
    care_access_pctile: 50,
    chronic_disease_pctile: null,
    behavioral_risk_pctile: null,
    mental_social_health_pctile: null,
    disability_pctile: null,
    socioeconomic_pctile: null,
    housing_transport_pctile: null,
    social_needs_pctile: null,
    digital_access_pctile: null,
    provider_supply_pctile: null,
    shortage_designation_pctile: null,
    safetynet_access_pctile: null,
    insurance_pctile: null,
    preventive_use_pctile: null,
    ...over,
  };
}
