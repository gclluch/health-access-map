"""build_providers: CMS NPPES full NPI file -> provider supply parquet (DuckDB).

Output columns (brief 12.6): zcta5(str5); providers_total, providers_primary,
providers_mental (int). Individuals only (Entity Type 1).

NPPES counts *registrations*, not capacity (brief 15.2): an NPI is not an FTE and
says nothing about Medicaid/uninsured acceptance. Labelled "registered providers".
The 10 GB extracted CSV is deleted only after the aggregate validates (brief 12.8).
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

import duckdb
import pandas as pd

from . import config
from .common import (assert_zcta, dev_prefix_sql, die, download_file,
                     http_client, log, write_provenance)

OUT = config.PROCESSED / "providers.parquet"
NPPES_ZIP = config.RAW / "NPPES_Data_Dissemination_June_2026_V2.zip"


# ---------------------------------------------------------------------------
# NUCC taxonomy crosswalk -> code -> {primary_care, mental_health, specialist, other}
# ---------------------------------------------------------------------------
def _resolve_nucc_url() -> str:
    try:
        with http_client(30) as c:
            html = c.get(config.NUCC_INDEX_URL).text
        links = re.findall(r'href="([^"]*nucc_taxonomy_(\d+)\.csv)"', html)
        if links:
            best = max(links, key=lambda t: int(t[1]))
            url = best[0]
            if url.startswith("/"):
                url = "https://www.nucc.org" + url
            return url
    except Exception as e:  # noqa: BLE001
        log("providers", f"NUCC index resolve failed ({type(e).__name__}); using seed")
    return config.NUCC_CSV_SEED


def _classify_row(grouping: str, classification: str, specialization: str) -> str:
    g, c, s = grouping.strip(), classification.strip(), specialization.strip().lower()
    # dentists -> dental access (own grouping)
    if g == config.DENTAL_GROUPING and c == "Dentist":
        return "dental"
    # mental health (psychiatrists are physicians; catch before primary/specialist)
    if g == config.MENTAL_HEALTH_GROUPING:
        return "mental_health"
    if c == config.MENTAL_HEALTH_CLASSIFICATION and "psychiatry" in s:
        return "mental_health"
    # maternity care: OB/GYN physicians (catch before the specialist fallback)
    if c == config.OBGYN_CLASSIFICATION:
        return "obgyn"
    # primary care: core PCP physician specialties + NP/PA
    if g == config.PHYSICIAN_GROUPING and c in config.PRIMARY_CARE_CLASSIFICATIONS:
        return "primary_care"
    if c in ("Nurse Practitioner", "Physician Assistant"):
        return "primary_care"
    if g == config.PHYSICIAN_GROUPING:
        return "specialist"
    return "other"


def _load_taxonomy_map() -> pd.DataFrame:
    url = _resolve_nucc_url()
    dest = config.RAW / Path(url).name
    download_file(url, dest, min_bytes=50_000)
    df = pd.read_csv(dest, dtype=str).fillna("")
    cols = {c.lower(): c for c in df.columns}
    code_c = cols.get("code")
    grp_c, cls_c, spec_c = cols.get("grouping"), cols.get("classification"), cols.get("specialization", "")
    if not (code_c and grp_c and cls_c):
        die("providers", f"NUCC csv missing Code/Grouping/Classification: {list(df.columns)}")
    out = pd.DataFrame({
        "code": df[code_c].str.strip(),
        "class": [
            _classify_row(g, c, df[spec_c].iloc[i] if spec_c else "")
            for i, (g, c) in enumerate(zip(df[grp_c], df[cls_c]))
        ],
    })
    out = out[out["code"] != ""].drop_duplicates("code")
    assert set(out["class"]).issubset(
        {"primary_care", "mental_health", "dental", "obgyn", "specialist", "other"})
    log("providers", f"NUCC {dest.name}: {len(out)} codes -> "
                     f"{(out['class']=='primary_care').sum()} primary, "
                     f"{(out['class']=='mental_health').sum()} mental, "
                     f"{(out['class']=='dental').sum()} dental, "
                     f"{(out['class']=='obgyn').sum()} obgyn")
    return out


# ---------------------------------------------------------------------------
# NPPES extraction + DuckDB aggregate
# ---------------------------------------------------------------------------
def _extract_main_csv() -> Path:
    if not NPPES_ZIP.exists():
        die("providers", f"NPPES zip not found: {NPPES_ZIP} (run download first)")
    with zipfile.ZipFile(NPPES_ZIP) as z:
        members = [
            m for m in z.namelist()
            if re.match(r"npidata_pfile_.*\.csv$", m, re.I)
            and "fileheader" not in m.lower()
        ]
        if not members:
            die("providers", f"no main npidata_pfile csv in {NPPES_ZIP.name}")
        main = max(members, key=lambda m: z.getinfo(m).file_size)
        dest = config.RAW / Path(main).name
        if dest.exists() and dest.stat().st_size > 1_000_000_000:
            log("providers", f"extracted CSV cached: {dest.name}")
            return dest
        log("providers", f"extracting {main} (~10 GB)...")
        z.extract(main, config.RAW)
    log("providers", f"extracted -> {dest.name} ({dest.stat().st_size/1e9:.1f} GB)")
    return dest


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("providers", f"skip (exists): {OUT.name}")
        return str(OUT)

    taxmap = _load_taxonomy_map()
    csv_path = _extract_main_csv()

    state_where = ""
    if dev_state:
        # filter on the practice-location state name to keep dev fast
        state_where = f"AND col_state = '{dev_state.upper()}'"

    con = duckdb.connect()
    con.register("taxmap", taxmap)
    log("providers", "DuckDB streaming aggregate over NPPES...")
    q = f"""
    WITH prov AS (
        SELECT
            "{config.NPPES_COL_POSTAL}"   AS postal,
            "{config.NPPES_COL_TAXONOMY}" AS taxonomy,
            "{config.NPPES_COL_STATE}"    AS col_state,
            "{config.NPPES_COL_CITY}"     AS city
        FROM read_csv('{csv_path}', all_varchar=true, ignore_errors=true,
                      header=true, quote='"', strict_mode=false)
        WHERE "{config.NPPES_COL_ENTITY}" = '1' {state_where}
    ),
    keyed AS (
        SELECT
            lpad(substr(regexp_replace(postal, '[^0-9]', '', 'g'), 1, 5), 5, '0') AS zcta5,
            COALESCE(taxmap."class", 'other') AS pclass,
            nullif(trim(city), '') AS city
        FROM prov LEFT JOIN taxmap ON prov.taxonomy = taxmap.code
    )
    SELECT
        zcta5,
        count(*)                                          AS providers_total,
        count(*) FILTER (WHERE pclass = 'primary_care')   AS providers_primary,
        count(*) FILTER (WHERE pclass = 'mental_health')  AS providers_mental,
        count(*) FILTER (WHERE pclass = 'dental')         AS providers_dental,
        count(*) FILTER (WHERE pclass = 'obgyn')          AS providers_obgyn,
        mode(city)                                        AS city
    FROM keyed
    WHERE zcta5 ~ '^[0-9]{{5}}$' AND zcta5 <> '00000'
    GROUP BY zcta5
    """
    df = con.execute(q).fetch_df()
    con.close()
    df["zcta5"] = df["zcta5"].astype("string")
    for c in ("providers_total", "providers_primary", "providers_mental",
              "providers_dental", "providers_obgyn"):
        df[c] = df[c].astype("int64")
    # NPPES cities are uppercase; title-case for display ("LOS ANGELES" -> "Los Angeles")
    df["city"] = df["city"].astype("string").str.title()

    _validate(df, dev_state)
    df.to_parquet(OUT, index=False)
    write_provenance({"providers": {
        "nppes_zip": NPPES_ZIP.name, "zctas": len(df),
        "providers_total": int(df["providers_total"].sum()),
        "scope": dev_state or "national",
    }})
    log("providers", f"wrote {OUT.name} ({len(df)} zctas, "
                     f"{df['providers_total'].sum():,} individual providers)")
    return str(OUT)


def cleanup_extracted() -> None:
    """Delete the multi-GB extracted CSV (call after national aggregate validates)."""
    for f in config.RAW.glob("npidata_pfile_*.csv"):
        if "fileheader" in f.name.lower():
            continue
        size = f.stat().st_size
        f.unlink()
        log("providers", f"deleted {f.name} (reclaimed {size/1e9:.1f} GB)")


def _validate(df: pd.DataFrame, dev_state: str | None) -> None:
    assert_zcta(df, stage="providers")
    total = int(df["providers_total"].sum())
    if dev_state:
        if len(df) < 200 or total < 20_000:
            die("providers", f"dev aggregate too small: {len(df)} zctas / {total} providers")
    else:
        if not (20_000 <= len(df) <= 35_000):
            die("providers", f"national zcta count {len(df)} outside 20k-35k")
        if total < 500_000:
            die("providers", f"providers_total sum {total} < 500k; column mapping likely wrong")
    log("providers", f"validated {len(df)} zctas, {total:,} providers, "
                     f"{int(df['providers_primary'].sum()):,} primary")


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)
