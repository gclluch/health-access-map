// Writes a tiny deterministic metrics.json + zcta_overview.geojson into public/ so the app can
// boot in CI without the multi-GB data build. A tiny zcta.pmtiles is also built when tippecanoe
// is on PATH (the overview alone covers the low zooms, so the smoke suite passes without it).
// No-ops if real payloads are already present, so it never clobbers a local `make data` build.
import { existsSync, writeFileSync, statSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const pub = join(dirname(fileURLToPath(import.meta.url)), '..', 'public');
const metricsPath = join(pub, 'metrics.json');
const geoPath = join(pub, 'zcta_overview.geojson');

// Treat a >5 KB metrics.json as a real build worth preserving.
const realExists = existsSync(metricsPath) && statSync(metricsPath).size > 5000;
if (realExists) {
  console.log('make-fixture: real metrics.json present, leaving payloads untouched');
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

const metrics = seed.map((s) => {
  const score = (35 * s.hn + 30 * s.sv + 35 * s.ca) / 100;
  return {
    zcta5: s.z, state: 'CA', state_name: 'California', city: s.city, county_name: 'Test County',
    population: 20000, life_expectancy: 80, life_expectancy_pctile: 50,
    access_gap_score: score, access_gap_pctile: score,
    access_gap_rank_lo: Math.max(0, score - 6), access_gap_rank_hi: Math.min(100, score + 6),
    access_gap_mult_pctile: score, tier: Math.ceil(score / 10), low_confidence: false, scoreable: true,
    health_need_pctile: s.hn, social_vulnerability_pctile: s.sv, care_access_pctile: s.ca,
    chronic_disease_pctile: s.hn, behavioral_risk_pctile: s.hn, mental_social_health_pctile: s.hn,
    disability_pctile: s.hn, socioeconomic_pctile: s.sv, housing_transport_pctile: s.sv,
    social_needs_pctile: s.sv, digital_access_pctile: s.sv, provider_supply_pctile: s.ca,
    shortage_designation_pctile: s.ca, safetynet_access_pctile: s.ca, insurance_pctile: s.ca,
    medical_debt_pctile: s.ca, preventive_use_pctile: s.ca,
  };
});

const geojson = {
  type: 'FeatureCollection',
  features: seed.map((s) => ({
    type: 'Feature', properties: { zcta5: s.z },
    geometry: { type: 'Polygon', coordinates: sq(s.lon, s.lat) },
  })),
};

writeFileSync(metricsPath, JSON.stringify(metrics));
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
console.log(`make-fixture: wrote ${metrics.length}-ZCTA fixture to public/`);
