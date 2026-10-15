import React, { useEffect, useMemo, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Circle, useMap } from 'react-leaflet';
import L from 'leaflet';
import { useLanguage } from '../../i18n/LanguageContext';
import { MapPin, Navigation, AlertCircle, Check } from 'lucide-react';
import { LOCATION_STATUS } from '../../hooks/useGeolocation';

// OpenStreetMap standard raster tiles. Using Leaflet's TileLayer (rather than
// the MapLibre vector layer) because raster OSM renders reliably across
// environments and never leaves grey/blank tiles after a resize.
const OSM_TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors';

// Recenter map helper + resize-safety so no grey tiles are left after the map
// container animates in or the window resizes.
function ChangeView({ center, zoom }) {
  const map = useMap();
  useEffect(() => {
    if (center) {
      map.setView(center, zoom || 15, { animate: true });
    }
  }, [center, zoom, map]);
  useEffect(() => {
    const t = setTimeout(() => map.invalidateSize(), 200);
    const onResize = () => map.invalidateSize();
    window.addEventListener('resize', onResize);
    return () => {
      clearTimeout(t);
      window.removeEventListener('resize', onResize);
    };
  }, [map]);
  return null;
}

// Custom Draggable Pin Icon
const createDraggableIcon = () => {
  return L.divIcon({
    className: 'custom-draggable-pin',
    html: `
      <div style="position: relative; width: 32px; height: 42px; transform: translate(-16px, -42px); cursor: grab;">
        <svg viewBox="0 0 24 24" width="32" height="42" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 0C7.58 0 4 3.58 4 8C4 13.5 12 24 12 24C12 24 20 13.5 20 8C20 3.58 16.42 0 12 0Z" fill="#e5484d" filter="drop-shadow(0 0 8px rgba(229,72,77,0.8))"/>
          <circle cx="12" cy="8" r="4" fill="#ffffff"/>
        </svg>
      </div>
    `,
    iconSize: [32, 42],
    iconAnchor: [16, 42],
  });
};

export const LocationPicker = ({
  consent,
  setConsent,
  status,
  coordinates,
  errorMessage,
  requestPosition,
  updateManualCoordinates,
  clearLocation,
  selectedArea,
  setSelectedArea,
}) => {
  const { t } = useLanguage();
  const markerRef = useRef(null);

  // Default center: Islamabad / Rawalpindi
  const defaultPosition = [33.6844, 73.0479];
  const position = coordinates ? [coordinates.lat, coordinates.lng] : defaultPosition;

  const draggableIcon = useMemo(() => createDraggableIcon(), []);

  const eventHandlers = useMemo(
    () => ({
      dragend() {
        const marker = markerRef.current;
        if (marker != null) {
          const newPos = marker.getLatLng();
          updateManualCoordinates(newPos.lat, newPos.lng, 10);
        }
      },
    }),
    [updateManualCoordinates]
  );

  const marketOptions = [
    'Raja Bazaar, Rawalpindi',
    'Saddar, Rawalpindi',
    'Commercial Market, Rawalpindi',
    'Committee Chowk, Rawalpindi',
    'Tench Bhata, Rawalpindi',
    'G-9 Markaz (Karachi Company), Islamabad',
    'F-10 Markaz, Islamabad',
    'F-7 Markaz, Islamabad',
    'Aabpara Market, Islamabad',
    'I-10 Sabzi Mandi, Islamabad',
    'PWD Housing Society, Islamabad',
    'Barakahu, Islamabad',
  ];

  return (
    <div className="space-y-4 rounded-3xl bg-[#0c0c0c]/80 border border-white/[0.08] p-5 md:p-6 backdrop-blur-xl">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400">
            <MapPin className="w-5 h-5" />
          </div>
          <div>
            <h4 className="text-sm md:text-base font-semibold text-white">
              {t.report.locationHeading}
            </h4>
            <p className="text-xs text-white/50">
              {t.report.locationSub}
            </p>
          </div>
        </div>

        {coordinates && (
          <button
            type="button"
            onClick={clearLocation}
            className="text-[11px] text-white/50 hover:text-white underline cursor-pointer"
          >
            {t.report.skipLocation}
          </button>
        )}
      </div>

      {/* Consent Card (Strict Gate) */}
      <div className="flex items-start gap-3 p-3.5 rounded-2xl bg-white/[0.03] border border-white/[0.06]">
        <input
          id="location-consent-checkbox"
          type="checkbox"
          checked={consent}
          onChange={(e) => {
            setConsent(e.target.checked);
            if (!e.target.checked) clearLocation();
          }}
          className="mt-0.5 h-4 w-4 rounded border-white/20 bg-black/40 text-violet-600 focus:ring-violet-500 cursor-pointer"
        />
        <label
          htmlFor="location-consent-checkbox"
          className="text-xs text-white/80 leading-relaxed cursor-pointer select-none"
        >
          {t.report.agreeLocation}
        </label>
      </div>

      {/* Consent Actions & GPS Trigger */}
      {consent && !coordinates && (
        <div className="space-y-3 animate-in fade-in duration-200">
          <div className="flex flex-col sm:flex-row items-center gap-3">
            <button
              type="button"
              onClick={requestPosition}
              disabled={status === LOCATION_STATUS.REQUESTING}
              className="w-full sm:w-auto flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white font-medium text-xs shadow-[0_0_20px_rgba(129,75,238,0.4)] transition-all cursor-pointer disabled:opacity-50"
            >
              <Navigation className={`w-4 h-4 ${status === LOCATION_STATUS.REQUESTING ? 'animate-spin' : ''}`} />
              <span>{status === LOCATION_STATUS.REQUESTING ? t.report.locating : t.report.useMyLocation}</span>
            </button>

            <span className="text-xs text-white/40">or pick market from list:</span>

            <select
              value={selectedArea}
              onChange={(e) => {
                setSelectedArea(e.target.value);
                // Rough coordinate matching for known markets
                const marketCoordinates = {
                  'Raja Bazaar, Rawalpindi': [33.6028, 73.0551],
                  'Saddar, Rawalpindi': [33.5962, 73.0538],
                  'Commercial Market, Rawalpindi': [33.6375, 73.0722],
                  'Committee Chowk, Rawalpindi': [33.6094, 73.0645],
                  'Tench Bhata, Rawalpindi': [33.5821, 73.0334],
                  'G-9 Markaz (Karachi Company), Islamabad': [33.6891, 73.0287],
                  'F-10 Markaz, Islamabad': [33.6938, 73.0112],
                  'F-7 Markaz, Islamabad': [33.7205, 73.0567],
                  'Aabpara Market, Islamabad': [33.7081, 73.0854],
                  'I-10 Sabzi Mandi, Islamabad': [33.6492, 73.0371],
                  'PWD Housing Society, Islamabad': [33.5852, 73.1384],
                  'Barakahu, Islamabad': [33.7423, 73.1876],
                };
                if (e.target.value && marketCoordinates[e.target.value]) {
                  const [lat, lng] = marketCoordinates[e.target.value];
                  updateManualCoordinates(lat, lng, 150);
                }
              }}
              className="w-full sm:w-auto flex-1 bg-[#131515] border border-white/10 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-violet-500"
            >
              <option value="">Select market/area...</option>
              {marketOptions.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* Geolocation errors remain visible after coordinates are captured. */}
      {consent && errorMessage && (
        <div className="flex items-start gap-2 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Interactive Map with Draggable Pin */}
      {consent && coordinates && (
        <div className="space-y-2 animate-in fade-in duration-300">
          <div className="relative h-56 md:h-64 rounded-2xl overflow-hidden border border-white/10 bg-[#080808] shadow-inner">
            <MapContainer
              center={position}
              zoom={16}
              scrollWheelZoom={false}
              className="w-full h-full z-0"
            >
              <ChangeView center={position} zoom={16} />
              <TileLayer
                url={OSM_TILE_URL}
                attribution={OSM_ATTRIBUTION}
                maxZoom={19}
                detectRetina={true}
              />

              {/* Accuracy Circle */}
              {typeof coordinates?.accuracy === 'number' && coordinates.accuracy >= 0 && (
                <Circle
                  center={position}
                  radius={coordinates.accuracy}
                  pathOptions={{
                    fillColor: '#e5484d',
                    fillOpacity: 0.15,
                    color: '#e5484d',
                    weight: 1,
                    dashArray: '4, 4',
                  }}
                />
              )}

              {/* Draggable Red Pin */}
              <Marker
                draggable={true}
                eventHandlers={eventHandlers}
                position={position}
                ref={markerRef}
                icon={draggableIcon}
              />
            </MapContainer>

            {/* Drag helper hint */}
            <div className="absolute bottom-2 left-2 right-2 z-[400] flex items-center justify-between px-3 py-1.5 rounded-lg bg-black/75 backdrop-blur-md text-[11px] text-white/80 border border-white/10 pointer-events-none">
              <span>{t.report.dragToAdjust}</span>
              <span className="font-mono text-white/50">
                ±{coordinates.accuracy}m
              </span>
            </div>
          </div>

          <div className="flex items-center justify-between text-xs text-white/60 px-1">
            <span className="flex items-center gap-1.5 text-emerald-400">
              <Check className="w-3.5 h-3.5" />
              <span>{t.report.locationCaptured}</span>
            </span>
            <span className="font-mono text-[11px] text-white/40">
              {coordinates.lat.toFixed(5)}, {coordinates.lng.toFixed(5)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

