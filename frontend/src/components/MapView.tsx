import { useEffect, useMemo, useRef, useState } from 'react';
import { Map, NavigationControl, useControl, type MapRef } from 'react-map-gl/maplibre';
import { WebMercatorViewport } from '@deck.gl/core';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { GeoJsonLayer } from '@deck.gl/layers';
import { useStore } from '../store';
import { metricValue } from '../lib/scoring';
import { buildQuantile, colorFor, SELECT_CASING, SELECT_LINE, CHROME, HOVER_LINE, IDLE_LINE } from '../lib/colors';
import { fmtScore } from '../lib/format';
import { metricLabel } from '../lib/types';

// Carto Positron - quiet light basemap. Mirrors pipeline/config.py BASEMAP_STYLE
// (cross-language, so it cannot be a shared import); keep the two in sync if changed.
const BASEMAP = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';

// deck.gl GeoJSON feature shape we read (single definition; used by every layer handler).
type ZctaFeature = { properties: { zcta5: string } };

function DeckOverlay(props: { layers: unknown[]; getTooltip?: (o: unknown) => unknown }) {
  // interleaved: the choropleth is inserted *beneath* the basemap's label/road layers
  // (via each layer's beforeId), so place names and roads stay legible on top of the fill.
  const overlay = useControl(() => new MapboxOverlay({ interleaved: true }));
  overlay.setProps(props as never);
  return null;
}

const REDUCE_MOTION =
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export default function MapView() {
  const mapRef = useRef<MapRef | null>(null);
  const { metrics, geojson, metric, weights, selectedZcta, hoveredZcta, bounds, flyTarget, fitTarget } =
    useStore();
  const select = useStore((s) => s.select);
  const hover = useStore((s) => s.hover);
  // id of the basemap's first label layer; the choropleth inserts beneath it so
  // roads + place names render on top (set on map load).
  const [labelLayerId, setLabelLayerId] = useState<string | undefined>(undefined);

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
      return { longitude: vp.longitude, latitude: vp.latitude, zoom: vp.zoom };
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
        duration: REDUCE_MOTION ? 0 : 1200,
      });
    }
  }, [flyTarget]);

  // Fit to a region (state quick-jump / clear-to-national).
  useEffect(() => {
    if (fitTarget && mapRef.current) {
      mapRef.current.fitBounds(fitTarget.bounds, { padding: 50, duration: REDUCE_MOTION ? 0 : 1100 });
    }
  }, [fitTarget]);

  const layer = useMemo(
    () =>
      new GeoJsonLayer({
        id: 'zcta',
        data: geojson as never,
        beforeId: labelLayerId, // insert beneath basemap labels/roads (interleaved)
        pickable: true,
        stroked: true,
        filled: true,
        lineWidthUnits: 'pixels',
        getFillColor: (f: ZctaFeature) => {
          const m = metrics.get(f.properties.zcta5);
          const v = m ? metricValue(m, metric, weights) : null;
          const [r, g, b] = colorFor(v, scale);
          // semi-transparent so the basemap (roads, place names) shows through;
          // "no reliable data" recedes further (quiet gray, §15.5).
          const alpha = v == null || Number.isNaN(v) ? 55 : 158;
          return [r, g, b, alpha];
        },
        getLineColor: (f: ZctaFeature) =>
          f.properties.zcta5 === hoveredZcta ? HOVER_LINE : IDLE_LINE,
        getLineWidth: (f: ZctaFeature) =>
          f.properties.zcta5 === hoveredZcta ? 1.5 : 0.3,
        onClick: (info: { object?: ZctaFeature }) => {
          if (info.object) select(info.object.properties.zcta5);
        },
        onHover: (info: { object?: ZctaFeature }) => {
          hover(info.object ? info.object.properties.zcta5 : null);
        },
        // smooth recolor when weights/metric change (§14.5); gentle, reduced-motion
        // respected by the browser at the CSS layer for the chrome.
        transitions: { getFillColor: { duration: REDUCE_MOTION ? 0 : 350 } },
        updateTriggers: {
          getFillColor: [metric, weights, scale],
          getLineColor: [selectedZcta, hoveredZcta],
          getLineWidth: [selectedZcta, hoveredZcta],
        },
      }),
    [geojson, metrics, metric, weights, scale, selectedZcta, hoveredZcta, select, hover, labelLayerId],
  );

  // Selection halo: a thick near-black casing under a bright white line, drawn as a
  // dedicated overlay so the selected ZIP reads clearly against BOTH ends of the ramp.
  const selectionLayers = useMemo(() => {
    if (!selectedZcta || !geojson) return [];
    const feats = (geojson as { features: ZctaFeature[] }).features;
    const feat = feats.find((f) => f.properties.zcta5 === selectedZcta);
    if (!feat) return [];
    const data = { type: 'FeatureCollection', features: [feat] } as never;
    const common = {
      data, stroked: true, filled: false, pickable: false,
      lineJointRounded: true, lineWidthUnits: 'pixels' as const,
    };
    return [
      new GeoJsonLayer({ ...common, id: 'sel-casing', getLineColor: SELECT_CASING,
        getLineWidth: 7, lineWidthMinPixels: 6 }),
      new GeoJsonLayer({ ...common, id: 'sel-line', getLineColor: SELECT_LINE,
        getLineWidth: 3, lineWidthMinPixels: 2.5 }),
    ];
  }, [selectedZcta, geojson]);

  const getTooltip = (info: { object?: ZctaFeature }) => {
    if (!info.object) return null;
    const z = info.object.properties.zcta5;
    const m = metrics.get(z);
    const v = m ? metricValue(m, metric, weights) : null;
    const place = m?.city ? `${m.city}, ${m.state ?? ''}` : m?.county_name ?? '';
    return {
      html: `<div style="font-family:'IBM Plex Sans',sans-serif;font-size:12px;line-height:1.35">
        ${place ? `<div style="font-weight:600">${place}</div>` : ''}
        <div style="font-family:'IBM Plex Mono',monospace;color:${CHROME.tooltipMono}">ZIP ${z} · ${metricLabel(metric)} <b style="color:#fff">${fmtScore(v)}</b></div></div>`,
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
      keyboard
      onLoad={(e) => {
        const style = (e.target as { getStyle: () => { layers: Array<{ id: string; type: string }> } }).getStyle();
        // first symbol (label) layer; roads sit just below it, so inserting the
        // choropleth here keeps both roads and labels on top.
        const firstSymbol = style?.layers?.find((l) => l.type === 'symbol');
        setLabelLayerId(firstSymbol?.id);
      }}
    >
      <NavigationControl position="bottom-right" showCompass={false} />
      <DeckOverlay layers={[layer, ...selectionLayers]} getTooltip={getTooltip as never} />
    </Map>
  );
}
