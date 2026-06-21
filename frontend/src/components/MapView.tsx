import { useEffect, useMemo, useRef } from 'react';
import { Map, NavigationControl, useControl, type MapRef } from 'react-map-gl/maplibre';
import { WebMercatorViewport } from '@deck.gl/core';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { GeoJsonLayer } from '@deck.gl/layers';
import { useStore } from '../store';
import { metricValue } from '../lib/scoring';
import { buildQuantile, colorFor, SELECTED_OUTLINE } from '../lib/colors';
import { fmtScore } from '../lib/format';
import { metricLabel } from '../lib/types';

const BASEMAP = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';

function DeckOverlay(props: { layers: unknown[]; getTooltip?: (o: unknown) => unknown }) {
  const overlay = useControl(() => new MapboxOverlay({ interleaved: false }));
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
        pickable: true,
        stroked: true,
        filled: true,
        lineWidthUnits: 'pixels',
        getFillColor: (f: { properties: { zcta5: string } }) => {
          const m = metrics.get(f.properties.zcta5);
          const v = m ? metricValue(m, metric, weights) : null;
          const [r, g, b] = colorFor(v, scale);
          // data polygons read solid; "no reliable data" recedes (quiet gray, §15.5).
          const alpha = v == null || Number.isNaN(v) ? 70 : 218;
          return [r, g, b, alpha];
        },
        getLineColor: (f: { properties: { zcta5: string } }) => {
          const z = f.properties.zcta5;
          if (z === selectedZcta) return SELECTED_OUTLINE;
          if (z === hoveredZcta) return [20, 84, 90, 200];
          return [255, 255, 255, 35];
        },
        getLineWidth: (f: { properties: { zcta5: string } }) =>
          f.properties.zcta5 === selectedZcta ? 2.5 : f.properties.zcta5 === hoveredZcta ? 1.5 : 0.3,
        onClick: (info: { object?: { properties: { zcta5: string } } }) => {
          if (info.object) select(info.object.properties.zcta5);
        },
        onHover: (info: { object?: { properties: { zcta5: string } } }) => {
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
    [geojson, metrics, metric, weights, scale, selectedZcta, hoveredZcta, select, hover],
  );

  const getTooltip = (info: { object?: { properties: { zcta5: string } } }) => {
    if (!info.object) return null;
    const z = info.object.properties.zcta5;
    const m = metrics.get(z);
    const v = m ? metricValue(m, metric, weights) : null;
    const place = m?.city ? `${m.city}, ${m.state ?? ''}` : m?.county_name ?? '';
    return {
      html: `<div style="font-family:'IBM Plex Sans',sans-serif;font-size:12px;line-height:1.35">
        ${place ? `<div style="font-weight:600">${place}</div>` : ''}
        <div style="font-family:'IBM Plex Mono',monospace;color:#C9CDd6">ZIP ${z} · ${metricLabel(metric)} <b style="color:#fff">${fmtScore(v)}</b></div></div>`,
      style: {
        background: '#14181F',
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
    >
      <NavigationControl position="bottom-right" showCompass={false} />
      <DeckOverlay layers={[layer]} getTooltip={getTooltip as never} />
    </Map>
  );
}
