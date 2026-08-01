import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxy dynamic API calls to FastAPI so the frontend uses same-origin /api.
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    // Split the large, stable vendor libs into their own chunks so a code change
    // doesn't bust their cache (deck.gl + maplibre dominate the bundle).
    rollupOptions: {
      output: {
        manualChunks: {
          // maplibre-gl and the deck.gl bundles import each other (deck's mapbox interop against
          // maplibre's types), so splitting them into two chunks emits a circular pair. They are
          // one dependency in practice and are upgraded together -- keep them in one chunk.
          mapvendor: [
            'maplibre-gl', 'react-map-gl',
            '@deck.gl/core', '@deck.gl/layers', '@deck.gl/mapbox', '@deck.gl/react',
          ],
          d3: ['d3-scale', 'd3-scale-chromatic', 'd3-array'],
        },
      },
    },
    // mapvendor is ~1.7 MB by design and is lazy-loaded, so it never blocks first paint.
    chunkSizeWarningLimit: 1800,
  },
});
