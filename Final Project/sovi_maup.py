"""
sovi_maup.py
============
Difference mapping of a SoVI-based social vulnerability index across
census block groups, tracts, and counties (SEES 3050 final project,
Elif Korkmaz).

Goal
----
Measure how much, and where, the mapped picture of social vulnerability
in a state changes when the same index is built for different census
units (the modifiable areal unit problem). Differences are mapped with
the unclassed choropleth difference mapping approach of Nelson (2026),
and ACS margins of error are carried through so that differences smaller
than sampling error are not read as unit effects.

Objectives
----------
O0  Prepare and describe the data (indicator maps, missing values, reliability).
O1  Build the index at each scale.
O2  Map where, and by how much, percentile ranks change between each pair
    of scales, by area and by population, masking unreliable differences.
O3  Compare agreement and index structure across scales.

Workflow (functions are grouped in the same order below)
--------
Step 1  Prepare data      load_config, download_variable_labels, download_acs,
                          download_boundaries, clean_acs, compute_indicators,
                          check_availability, screen_units, reliability_table,
                          prepare_data
        O0                describe_indicators, plot_indicator_maps, plot_correlation
Step 2  Build the index   standardize, varimax, build_index, additive_index,
                          build_all_indices, plot_index_maps
Step 3  Map differences   scale_pairs, difference_table, summarize_differences,
                          simulate_ranks, run_simulations, add_reliability,
                          plot_difference_maps, plot_difference_histograms
Step 4  Compare scales    compare_scales, top_share_agreement
Tests                     check_nesting, hand_check_table

run_all() runs every step and saves all tables and maps; it is used when the
file is run as a script (python sovi_maup.py). run_analysis.ipynb runs the
same steps one by one and shows the results.

All settings are read from config.toml. Paths are relative to the
repository folder. Raw downloads are saved in data/raw and never changed.
"""

import os
import time
import logging
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import requests
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

ACS_URL = "https://api.census.gov/data/{year}/acs/acs5"
TIGER_URL = "https://www2.census.gov/geo/tiger/TIGER{year}/{folder}/{file}"

# Short names used in file names for each scale
SCALE_CODE = {"block group": "bg", "tract": "tract", "county": "county"}

# Length of the GEOID at each scale (state 2 + county 3 + tract 6 + block group 1)
GEOID_LENGTH = {"county": 5, "tract": 11, "block group": 12}

# Total population, needed for screening and population-weighted summaries
POP_VAR = "B01003_001"

log = logging.getLogger("sovi_maup")

# Map colors. Sequential = one hue, light to dark (magnitude).
# Diverging = blue and red arms with a neutral gray middle (sign of a difference).
SEQ_CMAP = LinearSegmentedColormap.from_list(
    "seq_blue", ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
DIV_CMAP = LinearSegmentedColormap.from_list(
    "div_blue_red", ["#0d366b", "#3987e5", "#f0efec", "#e0604f", "#8e1b14"])
NO_DATA_COLOR = "#d9d9d6"


# =====================================================================
# Settings, folders, and logging
# =====================================================================

def load_config(path="config.toml"):
    """Read the settings file and return it as a dictionary."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Settings file not found: {path.resolve()}")
    with open(path, "rb") as f:
        cfg = tomllib.load(f)

    # Basic checks so that typos are caught early
    for section in ["study", "paths", "maps", "test", "download", "screening", "index", "uncertainty", "indicators"]:
        if section not in cfg:
            raise KeyError(f"config.toml is missing the [{section}] section")
    for scale in cfg["study"]["scales"]:
        if scale not in SCALE_CODE:
            raise ValueError(f"Unknown scale '{scale}'. Use: {list(SCALE_CODE)}")
    for ind in cfg["indicators"]:
        if ind["type"] not in ("value", "prop", "ratio"):
            raise ValueError(f"Indicator {ind['name']} has unknown type '{ind['type']}'")
        if ind["type"] != "value" and not ind["den"]:
            raise ValueError(f"Indicator {ind['name']} needs a denominator")
    return cfg


def setup_folders(cfg):
    """Create the data and output folders if they do not exist yet."""
    for key, folder in cfg["paths"].items():
        Path(folder).mkdir(parents=True, exist_ok=True)


def start_log(cfg):
    """Write messages both to the screen and to logs/run.log."""
    setup_folders(cfg)
    log.setLevel(logging.INFO)
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s  %(levelname)s  %(message)s", "%H:%M:%S")
    screen = logging.StreamHandler()
    screen.setFormatter(fmt)
    logfile = logging.FileHandler(Path(cfg["paths"]["logs"]) / "run.log", mode="a")
    logfile.setFormatter(fmt)
    log.addHandler(screen)
    log.addHandler(logfile)
    log.info("---- New run ----")


def get_api_key():
    """Read the Census API key from the CENSUS_API_KEY environment variable
    or from a file named census_api_key.txt (this file is not pushed to GitHub)."""
    key = os.environ.get("CENSUS_API_KEY")
    if not key and Path("census_api_key.txt").exists():
        key = Path("census_api_key.txt").read_text().strip()
    if not key:
        log.warning("No Census API key found. Cached raw files will be used if they exist.")
    return key


# =====================================================================
# Step 1a. Downloads (raw files are saved once and reused)
# =====================================================================

def add_to_metadata(cfg, file_name, source, status, note=""):
    """Record every download (file, source, status) in data/raw/metadata.csv."""
    metadata = Path(cfg["paths"]["raw"]) / "metadata.csv"
    row = pd.DataFrame([{"file": file_name, "source": source, "status": status, "note": note}])
    row.to_csv(metadata, mode="a", header=not metadata.exists(), index=False)


class RequestRefused(RuntimeError):
    """The server answered but refused the request (for example, a variable
    that is not published for this geography)."""


def web_get(url, cfg, params=None):
    """Download a URL. Retry a few times if the server is busy.
    Stop with a clear message if the request itself is wrong."""
    wait = cfg["download"]["wait_seconds"]
    tries = cfg["download"]["max_tries"]
    for attempt in range(1, tries + 1):
        try:
            r = requests.get(url, params=params, timeout=120)
        except requests.RequestException as err:
            log.warning(f"Try {attempt}/{tries} failed for {url}: {err}")
        else:
            if r.status_code == 200:
                return r
            # 4xx errors mean the request is wrong: retrying will not help
            if 400 <= r.status_code < 500:
                raise RequestRefused(f"Request refused ({r.status_code}) for {r.url}\n"
                                   f"Server message: {r.text[:300]}")
            log.warning(f"Try {attempt}/{tries}: server returned {r.status_code} for {url}")
        time.sleep(wait)
        wait *= 2
    add_to_metadata(cfg, url.split("/")[-1], url, "failed", f"no answer after {tries} tries")
    raise RuntimeError(f"Download failed after {tries} tries: {url}\n"
                       "Check your internet connection or try again later. "
                       "The same ACS tables are also available from NHGIS (www.nhgis.org).")


def acs_variable_list(cfg):
    """All ACS variable codes used by the indicators, plus total population."""
    codes = {POP_VAR}
    for ind in cfg["indicators"]:
        for code in ind["num"] + ind["den"]:
            codes.add(code.lstrip("-"))
    return sorted(codes)


def download_variable_labels(cfg):
    """Save the official label of every variable we use (for checking the config)."""
    out = Path(cfg["paths"]["raw"]) / f"acs{cfg['study']['acs_year']}_variable_labels.csv"
    if out.exists():
        return pd.read_csv(out)
    url = ACS_URL.format(year=cfg["study"]["acs_year"]) + "/groups/{table}.json"
    codes = acs_variable_list(cfg)
    rows = []
    for table in sorted({c.split("_")[0] for c in codes}):
        info = web_get(url.format(table=table), cfg).json()["variables"]
        for code in codes:
            if code.startswith(table + "_") and code + "E" in info:
                rows.append({"code": code, "label": info[code + "E"]["label"],
                             "concept": info[code + "E"].get("concept", "")})
    labels = pd.DataFrame(rows)
    missing = set(codes) - set(labels["code"])
    if missing:
        log.warning(f"These variables were not found in the ACS: {sorted(missing)}")
    labels.to_csv(out, index=False)
    add_to_metadata(cfg, out.name, url, "ok")
    return labels


def acs_request(cfg, fields, geo_for, geo_in, api_key):
    """One Census API request. Returns a DataFrame of text values."""
    params = {"get": ",".join(fields), "for": geo_for, "in": geo_in}
    if api_key:
        params["key"] = api_key
    rows = web_get(ACS_URL.format(year=cfg["study"]["acs_year"]), cfg, params).json()
    return pd.DataFrame(rows[1:], columns=rows[0])


def table_is_published(cfg, table_vars, scale, county_fips, api_key):
    """Ask for one variable of a table for one county. If the API refuses the
    request, the table is not published at this scale. (Other errors, such as a
    lost connection, are not caught here and stop the run with a message.)"""
    geo_for = {"block group": "block group:*", "tract": "tract:*", "county": "county:*"}[scale]
    geo_in = f"state:{cfg['study']['state_fips']}"
    if scale != "county":
        geo_in += f" county:{county_fips}"
    try:
        acs_request(cfg, [table_vars[0] + "E"], geo_for, geo_in, api_key)
        return True
    except RequestRefused:
        return False


def download_acs(cfg, scale, api_key):
    """Download estimates (E) and margins of error (M) for one scale and save
    them to data/raw. If the file is already there, read it instead."""
    st = cfg["study"]
    out = Path(cfg["paths"]["raw"]) / f"acs{st['acs_year']}_{st['state_abbr']}_{SCALE_CODE[scale]}.csv"
    if out.exists():
        log.info(f"Using saved file {out}")
        return pd.read_csv(out, dtype={"GEOID": str})
    if not api_key:
        raise RuntimeError(f"{out} does not exist and no API key was found. "
                           "Set CENSUS_API_KEY or create census_api_key.txt.")

    # Counties of the state (block groups must be requested county by county)
    counties = acs_request(cfg, ["NAME"], "county:*", f"state:{st['state_fips']}", api_key)
    county_list = sorted(counties["county"])

    # Check which tables are published at this scale
    codes = acs_variable_list(cfg)
    tables = {}
    for code in codes:
        tables.setdefault(code.split("_")[0], []).append(code)
    available = []
    for table, table_vars in tables.items():
        if table_is_published(cfg, table_vars, scale, county_list[0], api_key):
            available += table_vars
        else:
            log.warning(f"Table {table} is not published for {scale}s; its variables will be missing.")

    # Request the variables in chunks (the API has a limit on fields per request)
    fields = [c + s for c in available for s in ("E", "M")]
    size = cfg["download"]["vars_per_request"]
    chunks = [fields[i:i + size] for i in range(0, len(fields), size)]
    places = county_list if scale == "block group" else [None]
    geo_for = {"block group": "block group:*", "tract": "tract:*", "county": "county:*"}[scale]

    parts = []
    for place in places:
        geo_in = f"state:{st['state_fips']}" + (f" county:{place}" if place else "")
        pieces = [acs_request(cfg, chunk, geo_for, geo_in, api_key) for chunk in chunks]
        geo_cols = [c for c in ["state", "county", "tract", "block group"] if c in pieces[0].columns]
        merged = pieces[0]
        for p in pieces[1:]:
            merged = merged.merge(p, on=geo_cols)   # join chunks on the geography columns
        parts.append(merged)
        if place:
            log.info(f"  {scale}: county {place} done")
    raw = pd.concat(parts, ignore_index=True)

    # Build the GEOID from the geography columns
    geo_cols = ["state", "county", "tract", "block group"]
    raw["GEOID"] = raw[[c for c in geo_cols if c in raw.columns]].astype(str).agg("".join, axis=1)
    raw = raw[["GEOID"] + fields]
    raw.to_csv(out, index=False)
    add_to_metadata(cfg, out.name, ACS_URL.format(year=st["acs_year"]), "ok",
                    f"{len(raw)} units, {len(available)} variables")
    log.info(f"Saved {out} ({len(raw)} units)")
    return raw


def download_boundaries(cfg, scale):
    """Download TIGER/Line polygons for one scale, keep the study state,
    and project them to the equal-area CRS in the config."""
    st = cfg["study"]
    year = st["tiger_year"]
    if scale == "county":   # counties come as one national file
        folder, file = "COUNTY", f"tl_{year}_us_county.zip"
    else:
        folder = "BG" if scale == "block group" else "TRACT"
        file = f"tl_{year}_{st['state_fips']}_{SCALE_CODE[scale]}.zip"
    out = Path(cfg["paths"]["raw"]) / file
    url = TIGER_URL.format(year=year, folder=folder, file=file)
    if not out.exists():
        log.info(f"Downloading {url}")
        out.write_bytes(web_get(url, cfg).content)
        add_to_metadata(cfg, file, url, "ok")

    gdf = gpd.read_file(out)
    for col in ["GEOID", "STATEFP", "ALAND"]:
        if col not in gdf.columns:
            raise KeyError(f"Field {col} is missing from {file}")
    gdf = gdf[gdf["STATEFP"] == st["state_fips"]][["GEOID", "ALAND", "geometry"]].copy()
    if gdf.crs is None:
        raise ValueError(f"{file} has no coordinate system")
    gdf = gdf.to_crs(st["crs"])
    log.info(f"{scale}: {len(gdf)} polygons, projected to {gdf.crs.to_string()}")
    return gdf


# =====================================================================
# Step 1b. Indicators and their margins of error
# =====================================================================

def clean_acs(raw):
    """Split the raw table into estimates and MOEs (one column per variable)
    and replace the ACS special codes with missing values.
    ACS uses large negative numbers as flags, e.g. -666666666 = no estimate.
    A MOE of -555555555 means the value is controlled (exact), so MOE = 0."""
    raw = raw.set_index("GEOID")
    est = raw[[c for c in raw.columns if c.endswith("E")]].apply(pd.to_numeric, errors="coerce")
    moe = raw[[c for c in raw.columns if c.endswith("M")]].apply(pd.to_numeric, errors="coerce")
    est.columns = [c[:-1] for c in est.columns]
    moe.columns = [c[:-1] for c in moe.columns]
    est = est.mask(est < -100000)
    moe = moe.mask(moe == -555555555, 0)
    moe = moe.mask(moe < 0)
    return est, moe


def sum_with_moe(est, moe, codes):
    """Add (or subtract, for codes starting with '-') several ACS estimates.
    MOE of a sum or difference = square root of the sum of squared MOEs.
    Census rule for zero estimates: when several of the estimates are 0, only
    the largest of their MOEs is used (U.S. Census Bureau 2020, ch. 8)."""
    total = pd.Series(0.0, index=est.index)
    moe_sq = pd.Series(0.0, index=est.index)        # squared MOEs of non-zero estimates
    zero_moe = pd.Series(0.0, index=est.index)      # largest MOE among zero estimates
    for code in codes:
        name = code.lstrip("-")
        if name not in est.columns:          # table not published at this scale
            return pd.Series(np.nan, index=est.index), pd.Series(np.nan, index=est.index)
        sign = -1 if code.startswith("-") else 1
        total = total + sign * est[name]
        is_zero = est[name] == 0
        moe_sq = moe_sq + (moe[name] ** 2).where(~is_zero, 0)
        zero_moe = np.maximum(zero_moe, moe[name].where(is_zero, 0))
    return total, np.sqrt(moe_sq + zero_moe ** 2)


def compute_indicators(est, moe, cfg):
    """Compute every indicator and its MOE with the Census Bureau formulas.
    Proportion p = N/D:  MOE = sqrt(MOE_N^2 - p^2 * MOE_D^2) / D
                         (use + instead of - if the value under the root is negative)
    Ratio r = N/D:       MOE = sqrt(MOE_N^2 + r^2 * MOE_D^2) / D"""
    values, errors = {}, {}
    for ind in cfg["indicators"]:
        num, num_moe = sum_with_moe(est, moe, ind["num"])
        if ind["type"] == "value":
            values[ind["name"]], errors[ind["name"]] = num, num_moe
            continue
        den, den_moe = sum_with_moe(est, moe, ind["den"])
        den = den.where(den > 0)                      # avoid division by zero
        r = num / den
        if ind["type"] == "prop":
            inside = num_moe ** 2 - r ** 2 * den_moe ** 2
            inside = inside.where(inside >= 0, num_moe ** 2 + r ** 2 * den_moe ** 2)
            values[ind["name"]] = r * 100
            errors[ind["name"]] = np.sqrt(inside) / den * 100
        else:   # ratio
            values[ind["name"]] = r
            errors[ind["name"]] = np.sqrt(num_moe ** 2 + r ** 2 * den_moe ** 2) / den
    return pd.DataFrame(values), pd.DataFrame(errors)


def coefficient_of_variation(value, error, z=1.645):
    """CV (%) = (MOE / 1.645) / estimate * 100. Undefined when the estimate is 0."""
    return (error / z) / value.where(value != 0) * 100


# =====================================================================
# Step 1c. Screening
# =====================================================================

def check_availability(data, cfg):
    """Share of populated units with a missing value, for each indicator and scale.
    An indicator is kept only if the share is at most max_missing_share at every scale."""
    limit = cfg["screening"]["max_missing_share"]
    table = {}
    for scale, d in data.items():
        populated = d["pop"] >= cfg["screening"]["min_population"]
        table[scale] = d["values"][populated].isna().mean()
    avail = pd.DataFrame(table)
    avail["kept"] = (avail <= limit).all(axis=1)
    return avail


def screen_units(values, errors, pop, keep, cfg):
    """Remove units with no population or with a missing value in a kept indicator.
    Values are not filled in. Returns the clean tables and a short report."""
    report = {"units": len(values)}
    ok = pop >= cfg["screening"]["min_population"]
    report["dropped_no_population"] = int((~ok).sum())
    complete = values[keep].notna().all(axis=1)
    report["dropped_missing_values"] = int((ok & ~complete).sum())
    ok = ok & complete
    report["kept_units"] = int(ok.sum())
    return values.loc[ok, keep], errors.loc[ok, keep], pop[ok], report


def reliability_table(data, keep, cfg):
    """Median CV and share of units with low reliability (CV > cv_low)
    for each kept indicator and scale."""
    z = cfg["uncertainty"]["z_90"]
    rows = []
    for scale, d in data.items():
        cv = coefficient_of_variation(d["values"], d["errors"], z)
        for name in keep:
            rows.append({"indicator": name, "scale": scale,
                         "median_cv": cv[name].median(),
                         "share_cv_over_40": (cv[name] > cfg["uncertainty"]["cv_low"]).mean()})
    return pd.DataFrame(rows).pivot(index="indicator", columns="scale")


def prepare_data(cfg, api_key=None):
    """Run all of Step 1 for every scale.
    Returns a dictionary: scale -> {values, errors, pop, raw_est, raw_moe, gdf},
    the availability table, the kept indicators, and the screening report."""
    data = {}
    for scale in cfg["study"]["scales"]:
        log.info(f"== Preparing scale: {scale} ==")
        est, moe = clean_acs(download_acs(cfg, scale, api_key))
        values, errors = compute_indicators(est, moe, cfg)
        pop = est[POP_VAR] if POP_VAR in est.columns else pd.Series(np.nan, index=est.index)
        gdf = download_boundaries(cfg, scale)

        # Join check: every ACS unit should have a polygon and the reverse
        no_shape = set(values.index) - set(gdf["GEOID"])
        no_data = set(gdf["GEOID"]) - set(values.index)
        if no_shape:
            log.warning(f"{len(no_shape)} {scale}s have ACS data but no polygon, e.g. {sorted(no_shape)[:3]}")
        if no_data:
            log.warning(f"{len(no_data)} {scale} polygons have no ACS data, e.g. {sorted(no_data)[:3]}")
        data[scale] = {"values": values, "errors": errors, "pop": pop,
                       "raw_est": est, "raw_moe": moe, "gdf": gdf}

    avail = check_availability(data, cfg)
    keep = list(avail.index[avail["kept"]])
    dropped = list(avail.index[~avail["kept"]])
    log.info(f"Indicators kept: {len(keep)} of {len(avail)}. Dropped: {dropped}")

    report = {}
    for scale, d in data.items():
        d["values"], d["errors"], d["pop"], report[scale] = screen_units(
            d["values"], d["errors"], d["pop"], keep, cfg)
        log.info(f"{scale}: {report[scale]}")
    return data, avail, keep, pd.DataFrame(report).T


# =====================================================================
# O0. Describe the indicators (tables and maps)
# =====================================================================

def describe_indicators(data, keep):
    """Basic statistics of each kept indicator at each scale (after screening)."""
    rows = []
    for scale, d in data.items():
        for name in keep:
            x = d["values"][name]
            rows.append({"indicator": name, "scale": scale, "n": x.count(),
                         "mean": x.mean(), "sd": x.std(), "min": x.min(),
                         "median": x.median(), "max": x.max()})
    return pd.DataFrame(rows).set_index(["indicator", "scale"])


def map_layer(d, column_values):
    """Attach a column of values to the polygons of one scale (by GEOID)."""
    gdf = d["gdf"].set_index("GEOID")
    gdf["value"] = column_values.reindex(gdf.index)
    return gdf


def draw_panel(ax, gdf, outline, cmap, vmin, vmax, title):
    """One map panel: unclassed colors, gray for no data, county outlines on top."""
    gdf[gdf["value"].isna()].plot(ax=ax, color=NO_DATA_COLOR, linewidth=0)
    gdf[gdf["value"].notna()].plot(ax=ax, column="value", cmap=cmap,
                                   vmin=vmin, vmax=vmax, linewidth=0)
    outline.boundary.plot(ax=ax, color="white", linewidth=0.3)
    ax.set_title(title, fontsize=10)
    ax.set_axis_off()


def zoom_limits(cfg):
    """Projected x and y limits of the zoom box in the config."""
    w, s, e, n = cfg["maps"]["zoom_bbox"]
    box = gpd.GeoSeries.from_xy([w, e], [s, n], crs="EPSG:4326").to_crs(cfg["study"]["crs"])
    return (box.x.min(), box.x.max()), (box.y.min(), box.y.max())


def multi_scale_figure(data, cfg, column_values, cmap, vmin, vmax, label, title,
                       extend="neither", zoom=True):
    """Figure with one column per scale: the whole state on top and, if zoom
    is True, the zoom area below. column_values is a dictionary scale -> Series."""
    scales = list(data)
    outline = data[scales[-1]]["gdf"]
    xlim, ylim = zoom_limits(cfg)
    rows = 2 if zoom else 1
    fig, axes = plt.subplots(rows, len(scales), figsize=(4.2 * len(scales), 6.6 if zoom else 3.4),
                             gridspec_kw={"height_ratios": [0.75, 1]} if zoom else None,
                             squeeze=False)
    for j, scale in enumerate(scales):
        layer = map_layer(data[scale], column_values[scale])
        n = int(column_values[scale].notna().sum())
        draw_panel(axes[0, j], layer, outline, cmap, vmin, vmax, f"{scale.title()} (n = {n:,})")
        if not zoom:
            continue
        draw_panel(axes[1, j], layer, outline, cmap, vmin, vmax, cfg["maps"]["zoom_name"])
        axes[1, j].set_xlim(xlim)
        axes[1, j].set_ylim(ylim)
        # draw the zoom box on the state map
        axes[0, j].plot([xlim[0], xlim[1], xlim[1], xlim[0], xlim[0]],
                        [ylim[0], ylim[0], ylim[1], ylim[1], ylim[0]], color="black", linewidth=0.8)
    sm_ = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin, vmax))
    fig.colorbar(sm_, ax=axes, shrink=0.6, extend=extend, label=label)
    fig.suptitle(title, fontsize=11)
    return fig


def plot_indicator_maps(data, keep, cfg, labels=None):
    """For each indicator, save one figure with a panel per scale.
    All panels share one color range (2nd to 98th percentile of all values),
    so the same color means the same value on every panel."""
    folder = Path(cfg["paths"]["maps"]) / "indicators"
    folder.mkdir(parents=True, exist_ok=True)
    labels = labels or {ind["name"]: ind["label"] for ind in cfg["indicators"]}
    for name in keep:
        pooled = pd.concat([d["values"][name] for d in data.values()])
        vmin, vmax = pooled.quantile(0.02), pooled.quantile(0.98)
        values = {scale: d["values"][name] for scale, d in data.items()}
        fig = multi_scale_figure(data, cfg, values, SEQ_CMAP, vmin, vmax, labels.get(name, name),
                                 f"{name}: {labels.get(name, name)}", extend="both",
                                 zoom=cfg["maps"]["zoom_indicator_maps"])
        fig.savefig(folder / f"{name}.png", dpi=200, bbox_inches="tight")
        plt.close(fig)
    log.info(f"Saved {len(keep)} indicator maps to {folder}")


def plot_correlation(values, cfg, scale):
    """Heat map of Pearson correlations between the indicators at one scale."""
    corr = values.corr()
    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(corr, cmap=DIV_CMAP, vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr)), corr.columns, rotation=90, fontsize=7)
    ax.set_yticks(range(len(corr)), corr.columns, fontsize=7)
    fig.colorbar(im, ax=ax, shrink=0.8, label="Pearson correlation")
    ax.set_title(f"Correlation between indicators ({scale}s)")
    out = Path(cfg["paths"]["maps"]) / f"correlation_{SCALE_CODE[scale]}.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return corr


# =====================================================================
# Step 2. Build the index (O1)
#   2a standardize -> 2b PCA on the correlation matrix -> 2c keep components
#   -> 2d varimax rotation -> 2e set each component's direction
#   -> 2f add the component scores -> 2g percentile rank (0-100)
# =====================================================================

def standardize(values):
    """z-scores: (value - mean) / standard deviation, within one scale."""
    return (values - values.mean()) / values.std(ddof=0)


def varimax(loadings, max_iter=100, tol=1e-6):
    """Varimax rotation of a loading matrix (indicators x components).
    Standard algorithm (Kaiser 1958): rotate until the simplicity criterion
    stops improving. Returns the rotated loadings."""
    p, k = loadings.shape
    rotation = np.eye(k)
    last = 0
    for _ in range(max_iter):
        rotated = loadings @ rotation
        u, s, vt = np.linalg.svd(
            loadings.T @ (rotated ** 3 - rotated @ np.diag((rotated ** 2).sum(axis=0)) / p))
        rotation = u @ vt
        if s.sum() < last * (1 + tol):
            break
        last = s.sum()
    return loadings @ rotation


def directions(cfg):
    """Expected direction of each indicator (+1 or -1) from the config."""
    return pd.Series({ind["name"]: ind["direction"] for ind in cfg["indicators"]})


def build_index(values, cfg, structure=None):
    """Build the PCA-based index for one scale.

    values     DataFrame of indicators (rows = units).
    structure  None to fit a new PCA, or the structure of another scale
               to apply its components to these units (fixed-structure check).

    Returns (result, structure):
      result     DataFrame with the index score and its percentile rank (0-100)
      structure  dictionary with eigenvalues, rotated loadings, component
                 directions, and the score coefficients."""
    z = standardize(values)

    if structure is None:
        # 2b. PCA on the correlation matrix (eigenvalues and eigenvectors)
        corr = np.corrcoef(z.values, rowvar=False)
        eigval, eigvec = np.linalg.eigh(corr)
        order = np.argsort(eigval)[::-1]               # largest first
        eigval, eigvec = eigval[order], eigvec[:, order]

        # 2c. number of components to keep
        if cfg["index"]["retention"] == "kaiser":
            k = int((eigval > 1).sum())
        else:
            k = int(cfg["index"]["n_components"])

        # 2d. loadings (correlation of each indicator with each component), then varimax
        loadings = eigvec[:, :k] * np.sqrt(eigval[:k])
        rotated = varimax(loadings)

        # Score coefficients: component scores = z @ coef  (standardized scores)
        coef = rotated @ np.linalg.inv(rotated.T @ rotated)

        # 2e. direction of each component: look at the indicators with large loadings
        #     and check whether they point toward more or less vulnerability
        expected = directions(cfg).reindex(values.columns).values
        threshold = cfg["index"]["loading_threshold"]
        signs = []
        for j in range(k):
            big = np.abs(rotated[:, j]) >= threshold
            if not big.any():                       # no large loading: use the largest one
                big = np.abs(rotated[:, j]) == np.abs(rotated[:, j]).max()
            signs.append(1 if (rotated[big, j] * expected[big]).sum() >= 0 else -1)

        names = [f"PC{j + 1}" for j in range(k)]
        structure = {
            "indicators": list(values.columns),
            "eigenvalues": eigval,
            "n_components": k,
            "explained": eigval[:k] / eigval.sum(),
            "loadings": pd.DataFrame(rotated, index=values.columns, columns=names),
            "signs": pd.Series(signs, index=names),
            "coef": coef,
        }

    # Check that the same indicators are used, in the same order
    if list(values.columns) != structure["indicators"]:
        raise ValueError("Indicators do not match the structure being applied")

    # 2f. component scores, signed, then added with equal weight
    scores = z.values @ structure["coef"] * structure["signs"].values
    result = pd.DataFrame(scores, index=values.index, columns=structure["signs"].index)
    result["score"] = result.sum(axis=1)

    # 2g. percentile rank, 0 (least vulnerable) to 100 (most vulnerable)
    result["rank"] = result["score"].rank(pct=True) * 100
    return result, structure


def additive_index(values, cfg):
    """Simple additive index: sum of z-scores, each turned by its expected direction.
    Used as a robustness check against the PCA-based index."""
    z = standardize(values) * directions(cfg).reindex(values.columns)
    result = pd.DataFrame({"score": z.sum(axis=1)})
    result["rank"] = result["score"].rank(pct=True) * 100
    return result


def build_all_indices(data, cfg):
    """Loop over the scales: PCA index, additive index, and the fixed-structure
    index (the smallest scale's components applied to every scale).
    Results are stored in data[scale]["index"], ["additive"], ["fixed"]."""
    scales = cfg["study"]["scales"]
    structures = {}
    for scale in scales:
        values = data[scale]["values"]
        data[scale]["index"], structures[scale] = build_index(values, cfg)
        data[scale]["additive"] = additive_index(values, cfg)
        s = structures[scale]
        log.info(f"{scale}: {s['n_components']} components kept, "
                 f"{s['explained'].sum():.1%} of variance explained")
    base = structures[scales[0]]
    for scale in scales:
        data[scale]["fixed"], _ = build_index(data[scale]["values"], cfg, structure=base)
    return structures


def structure_table(structures):
    """One row per scale: units, components kept, variance explained,
    and the indicators that load strongly on each component."""
    rows = []
    for scale, s in structures.items():
        top = []
        for pc in s["loadings"].columns:
            col = s["loadings"][pc]
            strong = col[col.abs() >= 0.5].sort_values(key=abs, ascending=False)
            sign = "+" if s["signs"][pc] > 0 else "-"
            top.append(f"{pc}({sign}): " + ", ".join(strong.index[:4]))
        rows.append({"scale": scale, "components": s["n_components"],
                     "variance_explained": round(s["explained"].sum() * 100, 1),
                     "main_indicators": " | ".join(top)})
    return pd.DataFrame(rows).set_index("scale")


def plot_index_maps(data, cfg, column="index", title="PCA-based index"):
    """One figure with the percentile rank of the index at each scale."""
    values = {scale: d[column]["rank"] for scale, d in data.items()}
    fig = multi_scale_figure(data, cfg, values, SEQ_CMAP, 0, 100,
                             "Percentile rank (100 = most vulnerable)",
                             f"{title}: percentile rank within each scale")
    out = Path(cfg["paths"]["maps"]) / f"index_maps_{column}.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out


# =====================================================================
# Step 3. Map the differences (O2)
#   Nelson (2026): put each small unit next to the larger unit that contains
#   it, subtract, map the difference with an unclassed diverging scheme, and
#   report how much of the area (and here also the population) falls in each
#   range of difference. Because block groups nest in tracts and tracts in
#   counties, the larger unit is read from the first digits of the GEOID;
#   this gives the same result as Nelson's union overlay without a spatial join.
# =====================================================================

def scale_pairs(cfg):
    """All pairs (smaller scale, larger scale), e.g. block group-tract."""
    scales = cfg["study"]["scales"]
    return [(scales[i], scales[j]) for i in range(len(scales)) for j in range(i + 1, len(scales))]


def parent_ids(geoids, large):
    """GEOID of the larger unit that contains each smaller unit."""
    return pd.Series(geoids, index=geoids).str[:GEOID_LENGTH[large]]


def difference_table(data, small, large, column="index"):
    """For every small unit: its rank, the rank of its larger unit, the difference
    (small minus large), land area, and population.
    A positive difference means the small unit is more vulnerable than the
    larger unit's map shows."""
    small_rank = data[small][column]["rank"]
    parent = parent_ids(small_rank.index, large)
    large_rank = data[large][column]["rank"].reindex(parent.values)
    table = pd.DataFrame({"parent": parent.values,
                          "rank_small": small_rank.values,
                          "rank_large": large_rank.values}, index=small_rank.index)

    # Join check: every small unit should find its larger unit
    lost = table["rank_large"].isna().sum()
    if lost:
        log.warning(f"{small}-{large}: {lost} units have no ranked larger unit and are left out")
    table = table.dropna(subset=["rank_large"])

    table["diff"] = table["rank_small"] - table["rank_large"]
    land = data[small]["gdf"].set_index("GEOID")["ALAND"]
    table["area_km2"] = land.reindex(table.index).values / 1e6
    table["pop"] = data[small]["pop"].reindex(table.index).values
    return table


def weighted_share(mask, weights):
    """Share (%) of the total weight (area or population) where mask is True."""
    return 100 * weights[mask].sum() / weights.sum()


def summarize_differences(table, diff_col="diff"):
    """Nelson-style summary of one difference map: statistics, and the share of
    area and population within small and large differences."""
    d = table[diff_col]
    a, p = table["area_km2"], table["pop"]
    out = {"units": len(d), "min": d.min(), "max": d.max(), "mean": d.mean(),
           "sd": d.std(), "mean_abs": d.abs().mean()}
    for w_name, w in [("area", a), ("pop", p)]:
        out[f"{w_name}_within_5"] = weighted_share(d.abs() <= 5, w)
        out[f"{w_name}_within_10"] = weighted_share(d.abs() <= 10, w)
        out[f"{w_name}_over_20"] = weighted_share(d.abs() > 20, w)
        out[f"{w_name}_higher_than_large"] = weighted_share(d > 0, w)
    if "reliable" in table:
        r = table["reliable"]
        out["units_reliable"] = 100 * r.mean()
        out["area_reliable"] = weighted_share(r, a)
        out["pop_reliable"] = weighted_share(r, p)
    return out


# ---------- Margins of error: Monte Carlo simulation ----------

def simulate_ranks(d, cfg, structure, rng):
    """Repeat the index for one scale n_simulations times with indicator values
    drawn from their sampling distributions.

    Each indicator value is drawn from Normal(value, MOE / 1.645), where the MOE
    is the one computed with the Census Bureau formulas in compute_indicators.
    (Drawing the numerator and denominator separately would ignore that the
    numerator is part of the denominator and would overstate the error.)
    Percentages are kept between 0 and 100 and other values at 0 or more.
    The index is rebuilt with the SAME components, loadings, and directions as
    the main run (structure), so only the data change.
    Returns a DataFrame (units x simulations) of percentile ranks."""
    n_sim = cfg["uncertainty"]["n_simulations"]
    values = d["values"]
    se = d["errors"].fillna(0) / cfg["uncertainty"]["z_90"]   # missing MOE treated as 0
    is_percent = pd.Series({ind["name"]: ind["type"] == "prop" for ind in cfg["indicators"]})
    upper = np.where(is_percent.reindex(values.columns), 100, np.inf)

    ranks = np.empty((len(values), n_sim))
    for s in range(n_sim):
        draw = values + rng.standard_normal(values.shape) * se
        draw = draw.clip(lower=0, upper=upper, axis=1)
        result, _ = build_index(draw, cfg, structure=structure)
        ranks[:, s] = result["rank"].values
    return pd.DataFrame(ranks, index=values.index)


def run_simulations(data, structures, cfg):
    """Run simulate_ranks for every scale with one fixed random seed.
    Saves the simulated ranks in data/processed so they can be reused."""
    rng = np.random.default_rng(cfg["uncertainty"]["seed"])
    for scale, d in data.items():
        out = Path(cfg["paths"]["processed"]) / f"simulated_ranks_{SCALE_CODE[scale]}.csv"
        start = time.time()
        d["sim_ranks"] = simulate_ranks(d, cfg, structures[scale], rng)
        d["sim_ranks"].to_csv(out)
        width = (d["sim_ranks"].quantile(0.95, axis=1) - d["sim_ranks"].quantile(0.05, axis=1))
        log.info(f"{scale}: {cfg['uncertainty']['n_simulations']} simulations in "
                 f"{time.time() - start:.0f} s; median width of 90% rank interval = {width.median():.1f} points")


def add_reliability(table, data, small, large):
    """Add the simulated difference interval to a difference table.
    In every simulation: difference = small rank - larger unit's rank.
    A difference is reliable if its 90% interval (5th to 95th percentile)
    does not include 0."""
    sim_small = data[small]["sim_ranks"].loc[table.index].values
    sim_large = data[large]["sim_ranks"].loc[table["parent"]].values
    sim_diff = sim_small - sim_large
    table["diff_median"] = np.median(sim_diff, axis=1)
    table["diff_p05"] = np.percentile(sim_diff, 5, axis=1)
    table["diff_p95"] = np.percentile(sim_diff, 95, axis=1)
    table["reliable"] = (table["diff_p05"] > 0) | (table["diff_p95"] < 0)
    return table


# ---------- Difference maps and histograms ----------

def plot_difference_maps(data, table, small, large, cfg):
    """Difference map for one pair of scales. Left: all differences.
    Right: only reliable differences (unreliable units in gray).
    Top: whole state. Bottom: zoom area."""
    lim = cfg["maps"]["diff_limit"]
    gdf = data[small]["gdf"].set_index("GEOID").loc[table.index]
    outline = data[large]["gdf"]
    xlim, ylim = zoom_limits(cfg)
    columns = [("All differences", table["diff"])]
    if "reliable" in table:
        columns.append(("Reliable differences only (gray = within sampling error)",
                        table["diff"].where(table["reliable"])))
    fig, axes = plt.subplots(2, len(columns), figsize=(6 * len(columns), 8.2),
                             gridspec_kw={"height_ratios": [0.75, 1]}, squeeze=False)
    for j, (title, values) in enumerate(columns):
        layer = gdf.copy()
        layer["value"] = values
        draw_panel(axes[0, j], layer, outline, DIV_CMAP, -lim, lim, title)
        draw_panel(axes[1, j], layer, outline, DIV_CMAP, -lim, lim, cfg["maps"]["zoom_name"])
        axes[1, j].set_xlim(xlim)
        axes[1, j].set_ylim(ylim)
        axes[0, j].plot([xlim[0], xlim[1], xlim[1], xlim[0], xlim[0]],
                        [ylim[0], ylim[0], ylim[1], ylim[1], ylim[0]], color="black", linewidth=0.8)
    sm_ = plt.cm.ScalarMappable(cmap=DIV_CMAP, norm=plt.Normalize(-lim, lim))
    fig.colorbar(sm_, ax=axes, shrink=0.6, extend="both",
                 label=f"Rank difference ({small} minus {large})\n"
                       f"red = {small} more vulnerable than its {large} shows")
    fig.suptitle(f"Difference map: {small} minus {large} percentile rank", fontsize=12)
    out = Path(cfg["paths"]["maps"]) / f"difference_{SCALE_CODE[small]}_{SCALE_CODE[large]}.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_difference_histograms(tables, cfg):
    """Distribution of the differences for every pair, weighted by land area
    and by population (share of the state's total in each bin)."""
    step = cfg["maps"]["hist_bin"]
    bins = np.arange(-100, 100 + step, step)
    fig, axes = plt.subplots(1, len(tables), figsize=(4.6 * len(tables), 3.4), sharey=True)
    for ax, ((small, large), t) in zip(np.atleast_1d(axes), tables.items()):
        for weight, color, name in [("area_km2", "#1c5cab", "Land area"),
                                    ("pop", "#e0604f", "Population")]:
            share, _ = np.histogram(t["diff"], bins=bins, weights=t[weight] / t[weight].sum() * 100)
            ax.stairs(share, bins, color=color, linewidth=2, label=name)
        ax.axvline(0, color="#888888", linewidth=0.8)
        ax.set_title(f"{small} minus {large}", fontsize=10)
        ax.set_xlabel("Rank difference (points)")
        ax.grid(axis="y", color="#e6e6e3", linewidth=0.6)
        ax.spines[["top", "right"]].set_visible(False)
    np.atleast_1d(axes)[0].set_ylabel(f"% of state total per {step}-point bin")
    np.atleast_1d(axes)[0].legend(frameon=False)
    out = Path(cfg["paths"]["maps"]) / "difference_histograms.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out


# =====================================================================
# Step 4. Compare scales (O3)
# =====================================================================

def top_share_agreement(table, share):
    """Of the small units in the most vulnerable top share at their own scale,
    the percent whose larger unit is also in the top share (by units and by people)."""
    cut = 100 * (1 - share)
    top_small = table["rank_small"] > cut
    both = top_small & (table["rank_large"] > cut)
    return (100 * both.sum() / top_small.sum(),
            100 * table.loc[both, "pop"].sum() / table.loc[top_small, "pop"].sum())


def compare_scales(data, tables, cfg):
    """One row per pair of scales: rank agreement, top-20% agreement, share of
    reliable differences, and the two robustness checks (additive index and
    fixed-structure index), which repeat the difference map with another index."""
    share = cfg["index"]["top_share"]
    rows = []
    for (small, large), t in tables.items():
        units_top, pop_top = top_share_agreement(t, share)
        row = {"pair": f"{small} - {large}",
               "spearman_rank": t["rank_small"].corr(t["rank_large"], method="spearman"),
               f"top{int(share * 100)}_agree_units": units_top,
               f"top{int(share * 100)}_agree_pop": pop_top,
               "mean_abs_diff": t["diff"].abs().mean(),
               "reliable_units": 100 * t["reliable"].mean(),
               "reliable_pop": weighted_share(t["reliable"], t["pop"])}
        for check in ["additive", "fixed"]:
            other = difference_table(data, small, large, column=check)
            row[f"mean_abs_diff_{check}"] = other["diff"].abs().mean()
            row[f"diff_corr_{check}"] = t["diff"].corr(other["diff"].reindex(t.index), method="spearman")
        rows.append(row)
    return pd.DataFrame(rows).set_index("pair")

def zoom_summary(data, tables, cfg):
    """One row per pair of scales: how the zoom area of the maps (zoom_bbox in the
    config, e.g. the Denver metro) differs from the rest of the state, and how the
    largest 10% of small units (by land area) differ from their larger unit.
    A small unit is in the zoom area if a point inside its polygon falls in the box.
    These numbers explain why area and population shares differ."""
    xlim, ylim = zoom_limits(cfg)
    rows = []
    for (small, large), t in tables.items():
        pts = data[small]["gdf"].set_index("GEOID").representative_point().reindex(t.index)
        inside = ((pts.x >= xlim[0]) & (pts.x <= xlim[1]) &
                  (pts.y >= ylim[0]) & (pts.y <= ylim[1]))
        largest = t["area_km2"] >= t["area_km2"].quantile(0.9)
        rows.append({"pair": f"{small} - {large}",
                     "zoom_area": cfg["maps"]["zoom_name"],
                     "zoom_units_pct": 100 * inside.mean(),
                     "zoom_pop_pct": weighted_share(inside, t["pop"]),
                     "zoom_area_pct": weighted_share(inside, t["area_km2"]),
                     "reliable_in_zoom_pct": 100 * t.loc[inside, "reliable"].mean(),
                     "reliable_outside_pct": 100 * t.loc[~inside, "reliable"].mean(),
                     "mean_diff_in_zoom": t.loc[inside, "diff"].mean(),
                     "mean_diff_outside": t.loc[~inside, "diff"].mean(),
                     "largest10_ranked_higher_pct": 100 * (t.loc[largest, "diff"] > 0).mean(),
                     "largest10_mean_diff": t.loc[largest, "diff"].mean()})
    return pd.DataFrame(rows).set_index("pair")


# =====================================================================
# Tests
# =====================================================================

def check_nesting(data, cfg):
    """Test that the GEOID rule finds the right larger unit: a point inside each
    small polygon must fall inside the polygon of the larger unit named by its GEOID.
    Returns one row per pair with the percent of small units that pass."""
    rows = []
    for small, large in scale_pairs(cfg):
        pts = data[small]["gdf"].set_index("GEOID").representative_point()
        parents = parent_ids(pts.index, large)
        big = data[large]["gdf"].set_index("GEOID").geometry
        found = parents.isin(big.index)
        inside = pd.Series(False, index=pts.index)
        inside[found] = pts[found].within(big.reindex(parents[found].values), align=False).values
        rows.append({"pair": f"{small} - {large}", "small_units": len(pts),
                     "parent_found_pct": 100 * found.mean(),
                     "point_inside_parent_pct": 100 * inside.mean()})
        if not inside.all():
            log.warning(f"{small}-{large}: {(~inside).sum()} units fail the nesting test, "
                        f"e.g. {list(inside.index[~inside][:3])}")
    return pd.DataFrame(rows).set_index("pair")


def formula_text(ind):
    """Readable formula of an indicator, e.g. (A + B) / (C) * 100."""
    def terms(codes):
        text = " + ".join(codes).replace("+ -", "- ")
        return f"({text})" if len(codes) > 1 else text
    if ind["type"] == "value":
        return ind["num"][0]
    text = f"{terms(ind['num'])} / {terms(ind['den'])}"
    return text + " * 100" if ind["type"] == "prop" else text


def hand_check_table(data, cfg):
    """Small table for checking the code by hand: for a few random units at each
    scale, the raw ACS estimates and MOEs used by a few indicators, the formula,
    and the value and MOE computed by the code. The raw values can be looked up
    on data.census.gov and the formula redone with a calculator."""
    rng = np.random.default_rng(cfg["test"]["seed"])
    inds = {i["name"]: i for i in cfg["indicators"]}
    rows = []
    for scale, d in data.items():
        picks = rng.choice(d["values"].index, size=cfg["test"]["sample_units"], replace=False)
        for geoid in sorted(picks):
            for name in cfg["test"]["sample_indicators"]:
                ind = inds[name]
                codes = [c.lstrip("-") for c in ind["num"] + ind["den"]]
                raw = "; ".join(f"{c} = {d['raw_est'].at[geoid, c]:,.0f} ± {d['raw_moe'].at[geoid, c]:,.0f}"
                                for c in codes)
                rows.append({"scale": scale, "GEOID": geoid, "indicator": name,
                             "formula": formula_text(ind), "acs_values": raw,
                             "code_value": round(d["values"].at[geoid, name], 2),
                             "code_moe": round(d["errors"].at[geoid, name], 2)})
    return pd.DataFrame(rows)


# =====================================================================
# Run everything
# =====================================================================

def run_all(config_path="config.toml"):
    """Run Steps 1-4 and the tests, and save every table and map."""
    cfg = load_config(config_path)
    start_log(cfg)
    tables_dir = Path(cfg["paths"]["tables"])

    # Step 1 and O0
    download_variable_labels(cfg).to_csv(tables_dir / "variable_labels.csv", index=False)
    data, avail, keep, screening = prepare_data(cfg, get_api_key())
    avail.to_csv(tables_dir / "indicator_availability.csv")
    screening.to_csv(tables_dir / "screening_report.csv")
    reliability_table(data, keep, cfg).to_csv(tables_dir / "indicator_reliability.csv")
    describe_indicators(data, keep).to_csv(tables_dir / "indicator_statistics.csv")
    plot_indicator_maps(data, keep, cfg)
    plot_correlation(data[cfg["study"]["scales"][0]]["values"], cfg, cfg["study"]["scales"][0])

    # Step 2
    structures = build_all_indices(data, cfg)
    structure_table(structures).to_csv(tables_dir / "index_structure.csv")
    for scale, s in structures.items():
        s["loadings"].to_csv(tables_dir / f"loadings_{SCALE_CODE[scale]}.csv")
    plot_index_maps(data, cfg)
    plot_index_maps(data, cfg, "additive", "Additive index")

    # Step 3
    run_simulations(data, structures, cfg)
    tables = {}
    for small, large in scale_pairs(cfg):
        table = add_reliability(difference_table(data, small, large), data, small, large)
        table.to_csv(Path(cfg["paths"]["processed"]) /
                     f"differences_{SCALE_CODE[small]}_{SCALE_CODE[large]}.csv")
        plot_difference_maps(data, table, small, large, cfg)
        tables[(small, large)] = table
    pd.DataFrame({f"{s} - {l}": summarize_differences(t) for (s, l), t in tables.items()}
                 ).to_csv(tables_dir / "difference_summary.csv")
    plot_difference_histograms(tables, cfg)

    # Step 4 and tests
    compare_scales(data, tables, cfg).to_csv(tables_dir / "scale_comparison.csv")
    zoom_summary(data, tables, cfg).to_csv(tables_dir / "zoom_summary.csv")
    check_nesting(data, cfg).to_csv(tables_dir / "test_nesting.csv")
    log.info("Finished. Tables are in outputs/tables and maps in outputs/maps.")
    return data, tables


if __name__ == "__main__":
    run_all()
