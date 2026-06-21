// Member measures per sub-score (mirrors pipeline/taxonomy.py), used to render
// the deepest drill-down level from the full API record. unit drives formatting.
export type Unit = 'pct' | 'rate' | 'money' | 'per1k' | 'count' | 'km';
export interface Measure {
  col: string;
  label: string;
  unit: Unit;
  better?: 'high' | 'low'; // direction for context (default: low is better)
}

export const SUBSCORE_MEASURES: Record<string, Measure[]> = {
  chronic_disease: [
    { col: 'diabetes_pct', label: 'Diabetes', unit: 'pct' },
    { col: 'bphigh_pct', label: 'High blood pressure', unit: 'pct' },
    { col: 'highchol_pct', label: 'High cholesterol', unit: 'pct' },
    { col: 'chd_pct', label: 'Coronary heart disease', unit: 'pct' },
    { col: 'stroke_pct', label: 'Stroke', unit: 'pct' },
    { col: 'copd_pct', label: 'COPD', unit: 'pct' },
    { col: 'casthma_pct', label: 'Asthma', unit: 'pct' },
    { col: 'cancer_pct', label: 'Cancer', unit: 'pct' },
    { col: 'obesity_pct', label: 'Obesity', unit: 'pct' },
    { col: 'arthritis_pct', label: 'Arthritis', unit: 'pct' },
    { col: 'teethlost_pct', label: 'All teeth lost', unit: 'pct' },
  ],
  behavioral_risk: [
    { col: 'csmoking_pct', label: 'Current smoking', unit: 'pct' },
    { col: 'lpa_pct', label: 'No leisure physical activity', unit: 'pct' },
    { col: 'binge_pct', label: 'Binge drinking', unit: 'pct' },
    { col: 'sleep_pct', label: 'Short sleep (<7h)', unit: 'pct' },
  ],
  mental_social_health: [
    { col: 'depression_pct', label: 'Depression', unit: 'pct' },
    { col: 'mhlth_pct', label: 'Frequent poor mental-health days', unit: 'pct' },
    { col: 'loneliness_pct', label: 'Loneliness', unit: 'pct' },
    { col: 'emotionspt_pct', label: 'Lacks emotional support', unit: 'pct' },
  ],
  disability: [
    { col: 'disability_pct', label: 'Any disability', unit: 'pct' },
    { col: 'mobility_pct', label: 'Mobility', unit: 'pct' },
    { col: 'cognition_pct', label: 'Cognitive', unit: 'pct' },
    { col: 'vision_pct', label: 'Vision', unit: 'pct' },
    { col: 'hearing_pct', label: 'Hearing', unit: 'pct' },
    { col: 'selfcare_pct', label: 'Self-care', unit: 'pct' },
    { col: 'indeplive_pct', label: 'Independent living', unit: 'pct' },
  ],
  socioeconomic: [
    { col: 'poverty_rate', label: 'Below poverty', unit: 'rate' },
    { col: 'median_income', label: 'Median household income', unit: 'money', better: 'high' },
    { col: 'unemployment_rate', label: 'Unemployment', unit: 'rate' },
    { col: 'no_hs_diploma_rate', label: 'No high-school diploma', unit: 'rate' },
  ],
  housing_transport: [
    { col: 'no_vehicle_rate', label: 'No vehicle', unit: 'rate' },
    { col: 'crowding_rate', label: 'Crowded housing', unit: 'rate' },
    { col: 'mobile_home_rate', label: 'Mobile homes', unit: 'rate' },
    { col: 'multi_unit_rate', label: 'Multi-unit structures', unit: 'rate' },
  ],
  social_needs: [
    { col: 'foodinsecu_pct', label: 'Food insecurity', unit: 'pct' },
    { col: 'housinsecu_pct', label: 'Housing insecurity', unit: 'pct' },
    { col: 'lacktrpt_pct', label: 'Lack of transportation', unit: 'pct' },
    { col: 'shututility_pct', label: 'Utility shut-off threat', unit: 'pct' },
    { col: 'foodstamp_pct', label: 'Receives SNAP/food stamps', unit: 'pct' },
  ],
  provider_supply: [
    { col: 'primary_2sfca', label: 'Primary-care access (2SFCA)', unit: 'per1k', better: 'high' },
    { col: 'mental_2sfca', label: 'Mental-health access (2SFCA)', unit: 'per1k', better: 'high' },
    { col: 'dental_2sfca', label: 'Dental access (2SFCA)', unit: 'per1k', better: 'high' },
    { col: 'ob_2sfca', label: 'Maternity / OB-GYN access (2SFCA)', unit: 'per1k', better: 'high' },
  ],
  safetynet_access: [
    { col: 'fqhc_sites_reachable', label: 'FQHC sites within ~16 km', unit: 'count', better: 'high' },
    { col: 'nearest_fqhc_km', label: 'Nearest FQHC', unit: 'km' },
  ],
  insurance: [
    { col: 'uninsured_rate', label: 'Uninsured (all ages)', unit: 'rate' },
    { col: 'access2_pct', label: 'Uninsured adults 18-64', unit: 'pct' },
  ],
  preventive_use: [
    { col: 'checkup_pct', label: 'Annual checkup', unit: 'pct', better: 'high' },
    { col: 'dental_pct', label: 'Dental visit', unit: 'pct', better: 'high' },
    { col: 'cholscreen_pct', label: 'Cholesterol screening', unit: 'pct', better: 'high' },
    { col: 'mammouse_pct', label: 'Mammography', unit: 'pct', better: 'high' },
    { col: 'colon_screen_pct', label: 'Colorectal screening', unit: 'pct', better: 'high' },
    { col: 'bpmed_pct', label: 'Taking BP medication', unit: 'pct', better: 'high' },
  ],
};

export function fmtMeasure(v: unknown, unit: Unit): string {
  if (v == null || typeof v !== 'number' || Number.isNaN(v)) return '--';
  switch (unit) {
    case 'pct':
      return `${v.toFixed(1)}%`;
    case 'rate':
      return `${(v * 100).toFixed(1)}%`;
    case 'money':
      return `$${Math.round(v).toLocaleString('en-US')}`;
    case 'per1k':
      return `${v.toFixed(1)}/1k`;
    case 'count':
      return Math.round(v).toLocaleString('en-US');
    case 'km':
      return `${v.toFixed(1)} km`;
  }
}
