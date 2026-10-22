// Mirror of backend/zill/geo.py (CONTRACTS section 2). Local frame: x east, y up, z south.
export type Origin = { lat: number; lon: number };

const M_PER_DEG_LON_EQ = 111320;
const M_PER_DEG_LAT = 110574;

export function to_local(lat: number, lon: number, origin: Origin): [number, number] {
  const x = (lon - origin.lon) * M_PER_DEG_LON_EQ * Math.cos((origin.lat * Math.PI) / 180);
  const z = -(lat - origin.lat) * M_PER_DEG_LAT;
  return [x, z];
}

export function to_wgs84(x: number, z: number, origin: Origin): [number, number] {
  const lat = origin.lat - z / M_PER_DEG_LAT;
  const lon = origin.lon + x / (M_PER_DEG_LON_EQ * Math.cos((origin.lat * Math.PI) / 180));
  return [lat, lon];
}
