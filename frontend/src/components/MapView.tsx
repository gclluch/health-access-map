import { useEffect, useMemo, useRef, useState } from 'react';
import { Map, NavigationControl, useControl, type MapRef } from 'react-map-gl/maplibre';
import { WebMercatorViewport } from '@deck.gl/core';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { GeoJsonLayer } from '@deck.gl/layers';
import { TileLayer } from '@deck.gl/geo-layers';
import { ClipExtension } from '@deck.gl/extensions';
import { PMTiles } from 'pmtiles';
import { MVTLoader } from '@loaders.gl/mvt';
import { parse } from '@loaders.gl/core';
import { useStore } from '../store';
import { metricValue } from '../lib/scoring';
import { buildQuantile, colorFor, SELECT_LINE, CHROME, HOVER_LINE, IDLE_LINE } from '../lib/colors';
import { fmtScore } from '../lib/format';
import { metricLabel } from '../lib/types';

// Carto Positron - quiet light basemap. Mirrors pipeline/config.py BASEMAP_STYLE
// (cross-language, so it cannot be a shared import); keep the two in sync if changed.
const BASEMAP = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';

// Hybrid geometry renderer (see pipeline/build_pmtiles.py): below DETAIL_ZOOM the dense national
// choropleth draws from a small all-ZCTA overview (held in the store); at/above it, detailed
// geometry streams per-viewport from zcta.pmtiles. Vector tiles generalize low-zoom geometry to
// sub-pixel slivers, so tiles alone thin the national view - the overview keeps it dense.
const PM = new PMTiles('/zcta.pmtiles');
const TILE_MIN_ZOOM = 5; // mirrors -Z in pipeline/build_pmtiles.py
const TILE_MAX_ZOOM = 10; // mirrors -z; overzoomed past this
const DETAIL_ZOOM = 6; // overview below, streamed tiles at/above

type ZctaFeature = { properties: { zcta5: string } };

// Decode one tile from the PMTiles archive into WGS84 GeoJSON. Module-scope (referentially
// stable) so re-creating the TileLayer on a recolor never refetches/redecodes tiles - deck.gl
// reconciles by id and only re-runs the fill accessor.
async function getTileData(tile: {
  index: { x: number; y: number; z: number };
  signal?: AbortSignal;
}): Promise<ZctaFeature[] | null> {
  const { x, y, z } = tile.index;
  try {
    const t = await PM.getZxy(z, x, y, tile.signal);
    if (!t) return null;
    const gj = await parse(t.data, MVTLoader, {
      mvt: { coordinates: 'wgs84', tileIndex: { x, y, z }, layerProperty: 'layerName' },
    });
    return (gj as { features?: ZctaFeature[] }).features ?? (gj as unknown as ZctaFeature[]);
  } catch {
    // Missing/unreachable archive (e.g. a CI fixture with no tiles) -> draw nothing for this
    // tile rather than throwing; the overview still covers the low zooms.
    return null;
  }
}

// Escape any data-derived string before it enters the tooltip's innerHTML. Place names come
// from Census today (not user input), but the tooltip is a raw-HTML sink, so this removes the
// "one untrusted column from XSS" footgun rather than trusting the data source forever.
const ESC: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ESC[c]);
}

function DeckOverlay(props: { layers: unknown[]; getTooltip?: (o: unknown) => unknown }) {
  // interleaved: the choropleth is inserted *beneath* the basemap's label/road layers
  // (via beforeId), so place names and roads stay legible on top of the fill.
  const overlay = useControl(() => new MapboxOverlay({ interleaved: true }));
  overlay.setProps(props as never);
  return null;
}

const REDUCE_MOTION =
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export default function MapView() {
  const mapRef = useRef<MapRef | null>(null);
  const { metrics, overview, metric, weights, selectedZcta, hoveredZcta, bounds, flyTarget, fitTarget } =
    useStore();
  const select = useStore((s) => s.select);
  const hover = useStore((s) => s.hover);
  const [labelLayerId, setLabelLayerId] = useState<string | undefined>(undefined);
  // Which geometry source is live. Flipped only when the zoom crosses DETAIL_ZOOM (not on every
  // move) so layers aren't rebuilt continuously while panning.
  const [detail, setDetail] = useState(false);

  // Quantile color scale over the active metric's current value domain.
  const scale = useMemo(() => {
    const vals: number[] = [];
    for (const m of metrics.values()) {
      const v = metricValue(m, metric, weights);
      if (v != null && !Number.isNaN(v)) vals.push(v);
    }
    return buildQuantile(vals);
  }, [metrics, metric, weights]);

  // Deterministic initial view fitted to the data bounds (computed once at mount,
  // since MapView only renders after data is ready). Avoids fitBounds load-timing.
  const initialViewState = useMemo(() => {
    const fallback = { longitude: -98, latitude: 39, zoom: 3.6 };
    if (!bounds) return fallback;
    try {
      const vp = new WebMercatorViewport({
        width: window.innerWidth || 1280,
        height: window.innerHeight || 800,
      }).fitBounds(bounds, { padding: 60 });
      const narrow = window.innerWidth < 640;
      return {
        longitude: vp.longitude,
        latitude: vp.latitude,
        zoom: narrow ? Math.min(vp.zoom + 0.65, 4.2) : vp.zoom,
      };
    } catch {
      return fallback;
    }
  }, [bounds]);

  // Imperative fly-to driven by store.flyTarget.
  useEffect(() => {
    if (flyTarget && mapRef.current) {
      mapRef.current.flyTo({
        center: [flyTarget.longitude, flyTarget.latitude],
        zoom: flyTarget.zoom,
        duration: REDUCE_MOTION ? 0 : 650,
      });
    }
  }, [flyTarget]);

  // Fit to a region (state quick-jump / clear-to-national).
  useEffect(() => {
    if (fitTarget && mapRef.current) {
      mapRef.current.fitBounds(fitTarget.bounds, { padding: 50, duration: REDUCE_MOTION ? 0 : 700 });
    }
  }, [fitTarget]);

  // Shared fill/line accessors - identical join + colour for both the overview GeoJsonLayer and
  // the per-tile sublayers, so the choropleth looks the same across the hand-off.
  const fillColor = (f: ZctaFeature): [number, number, number, number] => {
    const m = metrics.get(f.properties.zcta5);
    const v = m ? metricValue(m, metric, weights) : null;
    const [r, g, b] = colorFor(v, scale);
    // semi-transparent so the basemap (roads, place names) shows through; "no reliable
    // data" recedes further (quiet gray, §15.5).
    const alpha = v == null || Number.isNaN(v) ? 55 : 158;
    return [r, g, b, alpha];
  };
  const lineColor = (f: ZctaFeature): [number, number, number, number] => {
    if (f.properties.zcta5 === selectedZcta) return SELECT_LINE;
    return f.properties.zcta5 === hoveredZcta ? HOVER_LINE : IDLE_LINE;
  };
  const lineWidth = (f: ZctaFeature): number => {
    if (f.properties.zcta5 === selectedZcta) return 3;
    return f.properties.zcta5 === hoveredZcta ? 1.5 : 0.3;
  };
  const onClickFeat = (info: { object?: ZctaFeature }) => {
    if (info.object) select(info.object.properties.zcta5);
  };
  const onHoverFeat = (info: { object?: ZctaFeature }) => {
    hover(info.object ? info.object.properties.zcta5 : null);
  };
  const fillTriggers = {
    getFillColor: [metric, weights, scale],
    getLineColor: [selectedZcta, hoveredZcta],
    getLineWidth: [selectedZcta, hoveredZcta],
  };

  // Low-zoom dense national choropleth (all ZCTAs, simplified overview geometry).
  const overviewLayer = useMemo(
    () =>
      new GeoJsonLayer({
        id: 'zcta-overview',
        data: overview as never,
        beforeId: labelLayerId,
        pickable: true,
        stroked: true,
        filled: true,
        lineWidthUnits: 'pixels',
        lineWidthMinPixels: 0.3,
        getFillColor: fillColor,
        getLineColor: lineColor,
        getLineWidth: lineWidth,
        onClick: onClickFeat,
        onHover: onHoverFeat,
        transitions: { getFillColor: { duration: REDUCE_MOTION ? 0 : 350 } },
        updateTriggers: fillTriggers,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [overview, metrics, metric, weights, scale, selectedZcta, hoveredZcta, labelLayerId],
  );

  // High-zoom streamed detail (vector tiles from pmtiles).
  const tileLayer = useMemo(
    () =>
      new TileLayer({
        id: 'zcta-tiles',
        getTileData,
        minZoom: TILE_MIN_ZOOM,
        maxZoom: TILE_MAX_ZOOM,
        renderSubLayers: ((props: {
          id: string;
          data: ZctaFeature[] | null;
          tile: { boundingBox: number[][] };
        }) => {
          if (!props.data) return null;
          // Clip each tile's features to its own bounds. tippecanoe buffers tiles, so edge
          // ZCTAs appear in adjacent tiles; without clipping the semi-transparent fills double
          // up into darker seams along the tile grid. This is what MVTLayer does internally.
          const bb = props.tile.boundingBox;
          const w = bb[0][0], s = bb[0][1], e = bb[1][0], n = bb[1][1];
          return new GeoJsonLayer({
            id: `${props.id}-fill`,
            data: props.data as never,
            beforeId: labelLayerId,
            pickable: true,
            stroked: true,
            filled: true,
            lineWidthUnits: 'pixels',
            lineWidthMinPixels: 0.3,
            lineJointRounded: true,
            getFillColor: fillColor,
            getLineColor: lineColor,
            getLineWidth: lineWidth,
            onClick: onClickFeat,
            onHover: onHoverFeat,
            transitions: { getFillColor: { duration: REDUCE_MOTION ? 0 : 350 } },
            updateTriggers: fillTriggers,
            extensions: [new ClipExtension()],
            clipBounds: [w, s, e, n],
          });
        }) as never,
        updateTriggers: {
          renderSubLayers: [metric, weights, scale, selectedZcta, hoveredZcta, labelLayerId],
        },
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [metrics, metric, weights, scale, selectedZcta, hoveredZcta, labelLayerId],
  );

  const layers = detail ? [tileLayer] : [overviewLayer];

  const getTooltip = (info: { object?: ZctaFeature }) => {
    if (!info.object) return null;
    const z = info.object.properties.zcta5;
    const m = metrics.get(z);
    const v = m ? metricValue(m, metric, weights) : null;
    const place = m?.city ? `${m.city}, ${m.state ?? ''}` : m?.county_name ?? '';
    const placeHtml = place ? `<div style="font-weight:600">${esc(place)}</div>` : '';
    return {
      html: `<div style="font-family:'IBM Plex Sans',sans-serif;font-size:12px;line-height:1.35">
        ${placeHtml}
        <div style="font-family:'IBM Plex Mono',monospace;color:${CHROME.tooltipMono}">ZIP ${esc(z)} · ${esc(metricLabel(metric))} <b style="color:#fff">${esc(fmtScore(v))}</b></div></div>`,
      style: {
        background: CHROME.ink,
        color: '#fff',
        padding: '4px 8px',
        borderRadius: '4px',
      },
    };
  };

  return (
    <Map
      ref={mapRef}
      initialViewState={initialViewState}
      mapStyle={BASEMAP}
      minZoom={TILE_MIN_ZOOM - 2}
      keyboard
      onMove={(e) => {
        const next = e.viewState.zoom >= DETAIL_ZOOM;
        setDetail((cur) => (cur === next ? cur : next));
      }}
      onLoad={(e) => {
        const style = (e.target as { getStyle: () => { layers: Array<{ id: string; type: string }> } }).getStyle();
        const firstSymbol = style?.layers?.find((l) => l.type === 'symbol');
        setLabelLayerId(firstSymbol?.id);
      }}
    >
      <NavigationControl position="bottom-right" showCompass={false} />
      <DeckOverlay layers={layers} getTooltip={getTooltip as never} />
    </Map>
  );
}
