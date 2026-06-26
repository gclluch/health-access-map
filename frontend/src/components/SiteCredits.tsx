import { useState } from 'react';

const REPO = 'https://github.com/gclluch/health-access-map';

// Data sources behind the displayed scoring map + outcome layer. All are public / U.S.-government
// datasets, each under its own terms (see docs/PRIMER.md for vintages + the per-source detail).
const SOURCES: Array<{ name: string; what: string; href: string }> = [
  { name: 'CDC PLACES', what: 'disease & health-need estimates', href: 'https://www.cdc.gov/places/' },
  { name: 'U.S. Census ACS 5-year', what: 'socioeconomic & insurance', href: 'https://www.census.gov/programs-surveys/acs' },
  { name: 'U.S. Census TIGER / Gazetteer', what: 'ZIP geography & centroids', href: 'https://www.census.gov/geographies/mapping-files.html' },
  { name: 'CMS NPPES', what: 'provider locations (supply)', href: 'https://npiregistry.cms.hhs.gov/' },
  { name: 'HRSA', what: 'shortage areas (HPSA) & health centers (FQHC)', href: 'https://data.hrsa.gov/' },
  { name: 'Urban Institute', what: 'medical debt in collections', href: 'https://datacatalog.urban.org/dataset/debt-america-2022' },
  { name: 'CDC USALEEP', what: 'small-area life expectancy (outcome)', href: 'https://www.cdc.gov/nchs/nvss/usaleep/usaleep.html' },
];

// "Sources & license" credit. Lives outside the methodology panel as a lightweight, always-present
// attribution + disclaimer for a public deployment (the basemap's own © CARTO / OpenStreetMap line
// is shown by the map control).
export default function SiteCredits() {
  const [open, setOpen] = useState(false);
  return (
    <div className="absolute z-20 left-2 bottom-1 sm:left-3 sm:bottom-2 hidden sm:block pointer-events-auto">
      {open && (
        <div
          role="dialog"
          aria-label="Sources and license"
          className="panel rounded-md p-3 mb-1.5 w-[300px] max-w-[88vw] text-[11px] leading-snug text-graphite shadow-lg"
        >
          <div className="font-medium text-ink mb-1.5">Data sources</div>
          <ul className="space-y-1">
            {SOURCES.map((s) => (
              <li key={s.name}>
                <a href={s.href} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
                  {s.name}
                </a>{' '}
                - {s.what}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-graphite">
            Validation outcomes (not scored): CDC WONDER treatable mortality, state ACSC/PQI panels,
            CDC overdose. Basemap © CARTO, © OpenStreetMap contributors.
          </p>
          <p className="mt-2 text-ink">
            A <strong>relative screening tool</strong> - not a clinical, diagnostic, or eligibility
            verdict, and not medical advice. Scores are national percentile ranks, not absolute quality.
          </p>
          <p className="mt-2">
            Open source (MIT) -{' '}
            <a href={REPO} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
              source & methodology
            </a>
          </p>
        </div>
      )}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="num text-[10px] text-graphite bg-surface/85 border border-hairline rounded px-1.5 py-1 hover:text-accent"
      >
        Sources &amp; license
      </button>
    </div>
  );
}
