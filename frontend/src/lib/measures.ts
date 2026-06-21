// Member measures per sub-score (mirrors pipeline/taxonomy.py), used to render
// the deepest drill-down level from the full API record. unit drives formatting;
// desc is the precise source definition, shown as a hover tooltip so a value like
// "Mammography 53.6%" is unambiguous.
export type Unit = 'pct' | 'rate' | 'money' | 'per1k' | 'count' | 'km';
export interface Measure {
  col: string;
  label: string;
  unit: Unit;
  desc?: string; // plain-English source definition (CDC PLACES / Census ACS)
  better?: 'high' | 'low'; // direction for context (default: low is better)
}

const PLACES = 'CDC PLACES model-based estimate (from BRFSS).';

export const SUBSCORE_MEASURES: Record<string, Measure[]> = {
  chronic_disease: [
    { col: 'diabetes_pct', label: 'Diabetes', unit: 'pct', desc: `Adults 18+ ever told they have diabetes (excludes gestational / pre-diabetes). ${PLACES}` },
    { col: 'bphigh_pct', label: 'High blood pressure', unit: 'pct', desc: `Adults 18+ ever told they have high blood pressure. ${PLACES}` },
    { col: 'highchol_pct', label: 'High cholesterol', unit: 'pct', desc: `Adults 18+ (ever screened) told they have high cholesterol. ${PLACES}` },
    { col: 'chd_pct', label: 'Coronary heart disease', unit: 'pct', desc: `Adults 18+ ever told they have coronary heart disease or angina. ${PLACES}` },
    { col: 'stroke_pct', label: 'Stroke', unit: 'pct', desc: `Adults 18+ ever told they had a stroke. ${PLACES}` },
    { col: 'copd_pct', label: 'COPD', unit: 'pct', desc: `Adults 18+ ever told they have COPD, emphysema, or chronic bronchitis. ${PLACES}` },
    { col: 'casthma_pct', label: 'Asthma', unit: 'pct', desc: `Adults 18+ who currently have asthma. ${PLACES}` },
    { col: 'cancer_pct', label: 'Cancer', unit: 'pct', desc: `Adults 18+ ever told they had cancer (excluding skin cancer). ${PLACES}` },
    { col: 'obesity_pct', label: 'Obesity', unit: 'pct', desc: `Adults 18+ with a body-mass index (BMI) of 30 or higher. ${PLACES}` },
    { col: 'arthritis_pct', label: 'Arthritis', unit: 'pct', desc: `Adults 18+ ever told they have some form of arthritis. ${PLACES}` },
    { col: 'teethlost_pct', label: 'All teeth lost', unit: 'pct', desc: `Adults 65+ who have lost all of their natural teeth. ${PLACES}` },
  ],
  behavioral_risk: [
    { col: 'csmoking_pct', label: 'Current smoking', unit: 'pct', desc: `Adults 18+ who currently smoke cigarettes (every day or some days). ${PLACES}` },
    { col: 'lpa_pct', label: 'No leisure physical activity', unit: 'pct', desc: `Adults 18+ reporting no leisure-time physical activity. ${PLACES}` },
    { col: 'binge_pct', label: 'Binge drinking', unit: 'pct', desc: `Adults 18+ who binge drink (5+ drinks for men / 4+ for women on an occasion). ${PLACES}` },
    { col: 'sleep_pct', label: 'Short sleep (<7h)', unit: 'pct', desc: `Adults 18+ who sleep less than 7 hours a night. ${PLACES}` },
  ],
  mental_social_health: [
    { col: 'depression_pct', label: 'Depression', unit: 'pct', desc: `Adults 18+ ever told they have a depressive disorder. ${PLACES}` },
    { col: 'mhlth_pct', label: 'Frequent poor mental-health days', unit: 'pct', desc: `Adults 18+ reporting 14+ days of poor mental health in the past month. ${PLACES}` },
    { col: 'loneliness_pct', label: 'Loneliness', unit: 'pct', desc: `Adults 18+ who report feeling socially isolated / lonely. ${PLACES}` },
    { col: 'emotionspt_pct', label: 'Lacks emotional support', unit: 'pct', desc: `Adults 18+ who rarely or never get the social/emotional support they need. ${PLACES}` },
  ],
  disability: [
    { col: 'disability_pct', label: 'Any disability', unit: 'pct', desc: `Adults 18+ reporting any disability. ${PLACES}` },
    { col: 'mobility_pct', label: 'Mobility', unit: 'pct', desc: `Adults 18+ with serious difficulty walking or climbing stairs. ${PLACES}` },
    { col: 'cognition_pct', label: 'Cognitive', unit: 'pct', desc: `Adults 18+ with serious difficulty concentrating, remembering, or deciding. ${PLACES}` },
    { col: 'vision_pct', label: 'Vision', unit: 'pct', desc: `Adults 18+ who are blind or have serious difficulty seeing. ${PLACES}` },
    { col: 'hearing_pct', label: 'Hearing', unit: 'pct', desc: `Adults 18+ who are deaf or have serious difficulty hearing. ${PLACES}` },
    { col: 'selfcare_pct', label: 'Self-care', unit: 'pct', desc: `Adults 18+ with difficulty dressing or bathing. ${PLACES}` },
    { col: 'indeplive_pct', label: 'Independent living', unit: 'pct', desc: `Adults 18+ with difficulty doing errands alone (shopping, doctor visits). ${PLACES}` },
  ],
  socioeconomic: [
    { col: 'poverty_rate', label: 'Below poverty', unit: 'rate', desc: 'Share of people with income below the federal poverty level. Census ACS 5-year (B17001).' },
    { col: 'median_income', label: 'Median household income', unit: 'money', better: 'high', desc: 'Median household income. Census ACS 5-year (B19013). Higher = less vulnerable.' },
    { col: 'unemployment_rate', label: 'Unemployment', unit: 'rate', desc: 'Unemployed as a share of the civilian labor force (16+). Census ACS 5-year (B23025).' },
    { col: 'no_hs_diploma_rate', label: 'No high-school diploma', unit: 'rate', desc: 'Adults 25+ without a high-school diploma. Census ACS 5-year (B15003).' },
  ],
  housing_transport: [
    { col: 'no_vehicle_rate', label: 'No vehicle', unit: 'rate', desc: 'Occupied housing units with no vehicle available. Census ACS 5-year (B25044).' },
    { col: 'crowding_rate', label: 'Crowded housing', unit: 'rate', desc: 'Occupied units with more than 1 occupant per room. Census ACS 5-year (B25014).' },
    { col: 'mobile_home_rate', label: 'Mobile homes', unit: 'rate', desc: 'Housing units that are mobile homes. Census ACS 5-year (B25024).' },
    { col: 'multi_unit_rate', label: 'Multi-unit structures', unit: 'rate', desc: 'Housing units in structures with 10+ units. Census ACS 5-year (B25024).' },
  ],
  social_needs: [
    { col: 'foodinsecu_pct', label: 'Food insecurity', unit: 'pct', desc: `Adults 18+ reporting food insecurity in the past 12 months. ${PLACES}` },
    { col: 'housinsecu_pct', label: 'Housing insecurity', unit: 'pct', desc: `Adults 18+ reporting housing insecurity in the past 12 months. ${PLACES}` },
    { col: 'lacktrpt_pct', label: 'Lack of transportation', unit: 'pct', desc: `Adults 18+ who lacked reliable transportation in the past 12 months. ${PLACES}` },
    { col: 'shututility_pct', label: 'Utility shut-off threat', unit: 'pct', desc: `Adults 18+ facing a utility shut-off threat in the past 12 months. ${PLACES}` },
    { col: 'foodstamp_pct', label: 'Receives SNAP/food stamps', unit: 'pct', desc: `Adults 18+ in households that received SNAP/food stamps in the past 12 months. ${PLACES}` },
  ],
  provider_supply: [
    { col: 'primary_2sfca', label: 'Primary-care access (2SFCA)', unit: 'per1k', better: 'high', desc: 'Primary-care providers per 1,000 people reachable within ~16 km, distance-decay weighted (E2SFCA). Higher = better access. Source: CMS NPPES.' },
    { col: 'mental_2sfca', label: 'Mental-health access (2SFCA)', unit: 'per1k', better: 'high', desc: 'Mental-health providers per 1,000 people reachable within ~16 km (E2SFCA). Higher = better. Source: CMS NPPES.' },
    { col: 'dental_2sfca', label: 'Dental access (2SFCA)', unit: 'per1k', better: 'high', desc: 'Dentists per 1,000 people reachable within ~16 km (E2SFCA). Higher = better. Source: CMS NPPES.' },
    { col: 'ob_2sfca', label: 'Maternity / OB-GYN access (2SFCA)', unit: 'per1k', better: 'high', desc: 'OB/GYN (maternity) providers per 1,000 people reachable within ~16 km (E2SFCA). Higher = better. Source: CMS NPPES.' },
  ],
  safetynet_access: [
    { col: 'fqhc_sites_reachable', label: 'FQHC sites within ~16 km', unit: 'count', better: 'high', desc: 'Number of HRSA Federally Qualified Health Center sites within ~16 km - sliding-fee clinics that serve everyone regardless of ability to pay.' },
    { col: 'nearest_fqhc_km', label: 'Nearest FQHC', unit: 'km', desc: 'Straight-line distance to the nearest FQHC (safety-net clinic).' },
  ],
  insurance: [
    { col: 'uninsured_rate', label: 'Uninsured (all ages)', unit: 'rate', desc: 'People of all ages with no health insurance coverage. Census ACS 5-year (B27001).' },
    { col: 'access2_pct', label: 'Uninsured adults 18-64', unit: 'pct', desc: `Adults aged 18-64 with no health insurance. ${PLACES}` },
  ],
  preventive_use: [
    { col: 'checkup_pct', label: 'Annual checkup', unit: 'pct', better: 'high', desc: `Adults 18+ who had a routine checkup in the past year. ${PLACES} Higher = better.` },
    { col: 'dental_pct', label: 'Dental visit', unit: 'pct', better: 'high', desc: `Adults 18+ who visited a dentist or dental clinic in the past year. ${PLACES} Higher = better.` },
    { col: 'cholscreen_pct', label: 'Cholesterol screening', unit: 'pct', better: 'high', desc: `Adults 18+ who had their cholesterol checked in the past 5 years. ${PLACES} Higher = better.` },
    { col: 'mammouse_pct', label: 'Mammography', unit: 'pct', better: 'high', desc: `Women aged 50-74 who had a mammogram in the past 2 years. ${PLACES} Higher = better.` },
    { col: 'colon_screen_pct', label: 'Colorectal screening', unit: 'pct', better: 'high', desc: `Adults aged 50-75 who are up to date on colorectal cancer screening. ${PLACES} Higher = better.` },
    { col: 'bpmed_pct', label: 'Taking BP medication', unit: 'pct', better: 'high', desc: `Adults 18+ with high blood pressure who are taking medication for it. ${PLACES} Higher = better.` },
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
