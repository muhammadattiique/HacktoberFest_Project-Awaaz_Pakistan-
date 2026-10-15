import React, {
  useEffect,
  useMemo,
  useRef,
  useState,
  useCallback,
} from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import { Crosshair, Search, X, MapPin } from 'lucide-react';

/**
 * InteractiveMap
 * ----------------------------------------------------------------------------
 * A self-contained, responsive interactive map built on React-Leaflet +
 * OpenStreetMap standard raster tiles.
 *
 * Features
 *  - Responsive container with a configurable height (default 500px).
 *  - Initial center / zoom (default Islamabad [33.6844, 73.0479], zoom 13).
 *  - OpenStreetMap contributor attribution (bottom-right).
 *  - Custom markers from an array of { id, name, description, lat, lng }.
 *  - Click a marker -> popup with name, description, and a "View Details" button.
 *  - Smooth zoom controls + drag/pan (Leaflet defaults).
 *  - "Recenter Map" button that animates back to the initial view.
 *  - Search/filter bar that highlights matches and flies to a single match.
 *  - Resize-safe (invalidateSize via ResizeObserver) -> no grey-tile glitches.
 *  - CSR-safe: Leaflet only touches window/document inside effects, and this
 *    component renders nothing map-related until mounted on the client.
 *
 * NOTE on markers: Leaflet's default marker icon URLs break under bundlers
 * (Vite/webpack). We use a lightweight inline SVG divIcon instead, matching
 * the project's existing marker style, so there is no missing-image issue and
 * no need to patch L.Icon.Default.
 */

const DEFAULT_CENTER = [33.6844, 73.0479]; // Islamabad
const DEFAULT_ZOOM = 13;

const OSM_TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors';

// Sample dataset (3-5 markers) so the map is interactive immediately.
export const SAMPLE_LOCATIONS = [
  {
    id: 'loc-1',
    name: 'Raja Bazaar',
    description: 'Historic central market in Rawalpindi. Reported price gouging on vegetables.',
    lat: 33.5977,
    lng: 73.0515,
  },
  {
    id: 'loc-2',
    name: 'G-9 Markaz',
    description: 'Islamabad commercial hub. Multiple overcharging complaints on kitchen staples.',
    lat: 33.6938,
    lng: 73.0291,
  },
  {
    id: 'loc-3',
    name: 'Aabpara Market',
    description: 'Food safety complaint: milk suspected of adulteration.',
    lat: 33.7076,
    lng: 73.0862,
  },
  {
    id: 'loc-4',
    name: 'Commercial Market, Satellite Town',
    description: 'Municipal issue: overflowing drain reported near the main road.',
    lat: 33.6428,
    lng: 73.0679,
  },
  {
    id: 'loc-5',
    name: 'Saddar Rawalpindi',
    description: 'Chicken sold well above the notified ceiling rate.',
    lat: 33.5944,
    lng: 73.0479,
  },
];

// Inline SVG pin as a Leaflet divIcon. `highlighted` enlarges + brightens it.
const createPinIcon = (highlighted = false) => {
  const w = highlighted ? 34 : 26;
  const h = highlighted ? 46 : 34;
  const glow = highlighted
    ? 'drop-shadow(0 0 10px rgba(229,72,77,0.95))'
    : 'drop-shadow(0 0 5px rgba(229,72,77,0.7))';
  return L.divIcon({
    className: 'interactive-map-pin',
    html: `
      <div style="position:relative;width:${w}px;height:${h}px;transform:translate(-${w / 2}px,-${h}px);transition:all .2s ease;">
        <svg viewBox="0 0 24 24" width="${w}" height="${h}" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 0C7.58 0 4 3.58 4 8C4 13.5 12 24 12 24C12 24 20 13.5 20 8C20 3.58 16.42 0 12 0Z" fill="#e5484d" style="filter:${glow}"/>
          <circle cx="12" cy="8" r="3.5" fill="#ffffff"/>
        </svg>
      </div>
    `,
    iconSize: [w, h],
    iconAnchor: [w / 2, h],
    popupAnchor: [0, -h + 6],
  });
};

// Imperative controller: exposes map actions to the parent via effects.
function MapController({ center, zoom, flyToTarget, onFlewTo, registerRecenter }) {
  const map = useMap();

  // Give the parent a stable "recenter" callback that animates home.
  useEffect(() => {
    registerRecenter(() => {
      map.flyTo(center, zoom, { duration: 1.1 });
    });
  }, [map, center, zoom, registerRecenter]);

  // Fly to a selected/searched marker.
  useEffect(() => {
    if (flyToTarget && Number.isFinite(flyToTarget.lat) && Number.isFinite(flyToTarget.lng)) {
      map.flyTo([flyToTarget.lat, flyToTarget.lng], Math.max(map.getZoom(), 15), {
        duration: 1.1,
      });
      onFlewTo();
    }
  }, [flyToTarget, map, onFlewTo]);

  // Resize handling: when the container size changes, tell Leaflet to recompute
  // so no grey/blank tiles are left behind.
  useEffect(() => {
    const container = map.getContainer();
    // Initial settle after mount/animation.
    const t = setTimeout(() => map.invalidateSize(), 200);

    let ro;
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(() => map.invalidateSize());
      ro.observe(container);
    }
    window.addEventListener('resize', () => map.invalidateSize());

    return () => {
      clearTimeout(t);
      if (ro) ro.disconnect();
    };
  }, [map]);

  return null;
}

export const InteractiveMap = ({
  locations = SAMPLE_LOCATIONS,
  center = DEFAULT_CENTER,
  zoom = DEFAULT_ZOOM,
  height = '500px',
  onViewDetails,
}) => {
  // CSR guard: never render Leaflet on the server. Vite is CSR, but this keeps
  // the component safe if dropped into an SSR framework (Next.js, etc.).
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const [query, setQuery] = useState('');
  const [flyToTarget, setFlyToTarget] = useState(null);
  const recenterRef = useRef(() => {});

  const validLocations = useMemo(
    () =>
      (locations || []).filter(
        (l) => Number.isFinite(Number(l.lat)) && Number.isFinite(Number(l.lng))
      ),
    [locations]
  );

  // Case-insensitive filter on name + description.
  const normalizedQuery = query.trim().toLowerCase();
  const matchedIds = useMemo(() => {
    if (!normalizedQuery) return new Set();
    return new Set(
      validLocations
        .filter(
          (l) =>
            l.name?.toLowerCase().includes(normalizedQuery) ||
            l.description?.toLowerCase().includes(normalizedQuery)
        )
        .map((l) => l.id)
    );
  }, [normalizedQuery, validLocations]);

  // When the query narrows to exactly one match, fly to it.
  useEffect(() => {
    if (normalizedQuery && matchedIds.size === 1) {
      const only = validLocations.find((l) => matchedIds.has(l.id));
      if (only) setFlyToTarget({ lat: Number(only.lat), lng: Number(only.lng) });
    }
  }, [normalizedQuery, matchedIds, validLocations]);

  const registerRecenter = useCallback((fn) => {
    recenterRef.current = fn;
  }, []);
  const handleFlewTo = useCallback(() => setFlyToTarget(null), []);

  const handleRecenter = () => {
    setQuery('');
    recenterRef.current?.();
  };

  const handleViewDetails = (loc) => {
    if (onViewDetails) onViewDetails(loc);
    // Default behaviour if no handler supplied: fly to the marker.
    else setFlyToTarget({ lat: Number(loc.lat), lng: Number(loc.lng) });
  };

  return (
    <div className="relative w-full">
      {/* Search / filter bar */}
      <div className="mb-3 flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search locations by name or description…"
            aria-label="Search map locations"
            className="w-full rounded-xl border border-white/10 bg-[#131515] py-2.5 pl-10 pr-9 text-sm text-white placeholder-white/40 focus:border-violet-500 focus:outline-none"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery('')}
              aria-label="Clear search"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-white/50 hover:text-white hover:bg-white/10 cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={handleRecenter}
          title="Recenter map to the default view"
          className="flex items-center gap-1.5 rounded-xl border border-white/15 bg-[#131515] px-3.5 py-2.5 text-xs font-semibold text-white/80 hover:text-white hover:bg-black/60 transition-colors cursor-pointer shrink-0"
        >
          <Crosshair className="w-4 h-4 text-violet-400" />
          <span className="hidden sm:inline">Recenter Map</span>
        </button>
      </div>

      {query && (
        <p className="mb-2 text-xs text-white/50">
          {matchedIds.size === 0
            ? 'No locations match your search.'
            : `${matchedIds.size} location${matchedIds.size > 1 ? 's' : ''} highlighted.`}
        </p>
      )}

      {/* Map container */}
      <div
        className="relative w-full overflow-hidden rounded-3xl border border-white/10 bg-[#030014]"
        style={{ height }}
      >
        {mounted ? (
          <MapContainer
            center={center}
            zoom={zoom}
            scrollWheelZoom={true}
            zoomControl={true}
            className="w-full h-full z-0"
          >
            <TileLayer
              url={OSM_TILE_URL}
              attribution={OSM_ATTRIBUTION}
              maxZoom={19}
              detectRetina={true}
            />

            <MapController
              center={center}
              zoom={zoom}
              flyToTarget={flyToTarget}
              onFlewTo={handleFlewTo}
              registerRecenter={registerRecenter}
            />

            {validLocations.map((loc) => {
              const isHighlighted = matchedIds.has(loc.id);
              // When a search is active, dim non-matches for visual focus.
              const dimmed = normalizedQuery && !isHighlighted;
              return (
                <Marker
                  key={loc.id}
                  position={[Number(loc.lat), Number(loc.lng)]}
                  icon={createPinIcon(isHighlighted)}
                  opacity={dimmed ? 0.35 : 1}
                >
                  <Popup className="interactive-map-popup">
                    <div className="min-w-[210px] rounded-xl border border-white/10 bg-[#0c0c0c] p-3 text-white">
                      <div className="mb-1 flex items-center gap-1.5">
                        <MapPin className="w-3.5 h-3.5 shrink-0 text-rose-400" />
                        <span className="text-sm font-bold text-rose-300">{loc.name}</span>
                      </div>
                      <p className="mb-2.5 text-xs leading-relaxed text-white/70">
                        {loc.description}
                      </p>
                      <button
                        type="button"
                        onClick={() => handleViewDetails(loc)}
                        className="w-full rounded-lg bg-gradient-to-r from-[#814bee] to-[#4f1ad6] py-1.5 text-center text-xs font-semibold text-white transition-opacity hover:opacity-90 cursor-pointer"
                      >
                        View Details
                      </button>
                    </div>
                  </Popup>
                </Marker>
              );
            })}
          </MapContainer>
        ) : (
          // CSR placeholder (shown during SSR / before client mount).
          <div className="flex h-full w-full items-center justify-center text-sm text-white/40">
            Loading map…
          </div>
        )}
      </div>
    </div>
  );
};

export default InteractiveMap;
