// Average all coordinate pairs in an arbitrarily-nested GeoJSON coordinate array (a cheap
// label-point centroid). Shared by the main-thread loader (data.ts) and the off-thread data
// worker (dataWorker.ts) so the two stay in lockstep. Falls back to a CONUS-ish point if empty.
export function centroid(coords: unknown): [number, number] {
  let sx = 0;
  let sy = 0;
  let n = 0;
  const walk = (c: unknown) => {
    if (Array.isArray(c) && typeof c[0] === 'number' && typeof c[1] === 'number') {
      sx += c[0] as number;
      sy += c[1] as number;
      n += 1;
    } else if (Array.isArray(c)) {
      c.forEach(walk);
    }
  };
  walk(coords);
  return n ? [sx / n, sy / n] : [-119, 37];
}
