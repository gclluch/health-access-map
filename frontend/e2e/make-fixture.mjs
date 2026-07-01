// Writes a tiny deterministic map_frame.json + subscores.json + zcta_overview.geojson into public/ so
// the app can boot in CI without the multi-GB data build. A tiny zcta.pmtiles is also built when
// tippecanoe is on PATH (the overview alone covers the low zooms, so the smoke suite passes without it).
// No-ops if real payloads are already present, so it never clobbers a local `make data` build.
import { existsSync, writeFileSync, statSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const pub = join(dirname(fileURLToPath(import.meta.url)), '..', 'public');
const framePath = join(pub, 'map_frame.json');
const subscoresPath = join(pub, 'subscores.json');
const geoPath = join(pub, 'zcta_overview.geojson');

// Treat a >5 KB map_frame.json as a real build worth preserving.
const realExists = existsSync(framePath) && statSync(framePath).size > 5000;
if (realExists) {
  console.log('make-fixture: real map_frame.json present, leaving payloads untouched');
  process.exit(0);
}

// Five ZCTAs around California with spread-out dimension percentiles.
const seed = [
  { z: '90001', city: 'Los Angeles', lon: -118.24, lat: 33.97, hn: 95, sv: 92, ca: 88 },
  { z: '90210', city: 'Beverly Hills', lon: -118.41, lat: 34.1, hn: 12, sv: 8, ca: 15 },
  { z: '93725', city: 'Fresno', lon: -119.74, lat: 36.66, hn: 78, sv: 81, ca: 70 },
  { z: '95814', city: 'Sacramento', lon: -121.49, lat: 38.58, hn: 55, sv: 50, ca: 45 },
  { z: '92101', city: 'San Diego', lon: -117.16, lat: 32.72, hn: 40, sv: 35, ca: 60 },
];

const sq = (lon, lat, d = 0.1) => [[
  [lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d],
]];

// Full per-ZCTA record; split below into the columnar frame + subscores payloads (mirrors the
// pipeline's join_and_score._write_map_frame / _write_subscores partition).
const records = seed.map((s) => {
  const score = Math.round((35 * s.hn + 30 * s.sv + 35 * s.ca) / 100);
  return {
    zcta5: s.z, state: 'CA', city: s.city, county_name: 'Test County', population: 20000,
    health_need_pctile: s.hn, social_vulnerability_pctile: s.sv, care_access_pctile: s.ca,
    access_gap_pctile: score, access_gap_pctile_within_state: score, care_access_resid_pctile: score,
    access_gap_rank_lo: Math.max(0, score - 6), access_gap_rank_hi: Math.min(100, score + 6),
    tier: Math.ceil(score / 10), n_dims_scored: 3, low_confidence: 0, institutional: 0, scoreable: 1,
    life_expectancy_pctile: 50,
    chronic_disease_pctile: s.hn, behavioral_risk_pctile: s.hn, mental_social_health_pctile: s.hn,
    disability_pctile: s.hn, socioeconomic_pctile: s.sv, housing_transport_pctile: s.sv,
    social_needs_pctile: s.sv, digital_access_pctile: s.sv, provider_supply_pctile: s.ca,
    shortage_designation_pctile: s.ca, safetynet_access_pctile: s.ca, insurance_pctile: s.ca,
    medical_debt_pctile: s.ca, preventive_use_pctile: s.ca,
  };
});

const columnar = (cols) => {
  const out = { n: records.length };
  for (const c of cols) out[c] = records.map((r) => r[c]);
  return out;
};

const FRAME_COLS = ['zcta5', 'state', 'city', 'county_name', 'population',
  'health_need_pctile', 'social_vulnerability_pctile', 'care_access_pctile',
  'access_gap_pctile', 'access_gap_pctile_within_state', 'care_access_resid_pctile',
  'access_gap_rank_lo', 'access_gap_rank_hi',
  'tier', 'n_dims_scored', 'low_confidence', 'institutional', 'scoreable'];
const SUBSCORE_COLS = ['zcta5',
  'chronic_disease_pctile', 'behavioral_risk_pctile', 'mental_social_health_pctile', 'disability_pctile',
  'socioeconomic_pctile', 'housing_transport_pctile', 'social_needs_pctile', 'digital_access_pctile',
  'provider_supply_pctile', 'shortage_designation_pctile', 'safetynet_access_pctile', 'insurance_pctile',
  'medical_debt_pctile', 'preventive_use_pctile', 'life_expectancy_pctile'];

const geojson = {
  type: 'FeatureCollection',
  features: seed.map((s) => ({
    type: 'Feature', properties: { zcta5: s.z },
    geometry: { type: 'Polygon', coordinates: sq(s.lon, s.lat) },
  })),
};

writeFileSync(framePath, JSON.stringify(columnar(FRAME_COLS)));
writeFileSync(subscoresPath, JSON.stringify(columnar(SUBSCORE_COLS)));
writeFileSync(geoPath, JSON.stringify(geojson));

// Detailed geometry tiles (only used at z>=6). Best-effort: build from the fixture geojson if
// tippecanoe is available, otherwise skip - getTileData tolerates a missing archive.
try {
  execFileSync('tippecanoe', ['-q', '--force', '-Z5', '-z10', '--no-tile-size-limit',
    '--no-feature-limit', '-l', 'zcta', '-o', join(pub, 'zcta.pmtiles'), geoPath], { stdio: 'ignore' });
  console.log('make-fixture: built zcta.pmtiles');
} catch {
  console.log('make-fixture: tippecanoe not found, skipping zcta.pmtiles (overview covers smoke)');
}
console.log(`make-fixture: wrote ${records.length}-ZCTA fixture to public/`);
