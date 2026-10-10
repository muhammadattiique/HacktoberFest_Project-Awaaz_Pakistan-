import React, { useEffect, useRef, useState, useMemo } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import { Maximize2, RefreshCw } from 'lucide-react';

// Custom Map Controller for programmatic Fit All & non-intrusive pan
function MapController({ complaints, shouldFitBounds, onBoundsFitted, selectedComplaint }) {
  const map = useMap();

  // Focus selected complaint if changed
  useEffect(() => {
    if (selectedComplaint && selectedComplaint.lat && selectedComplaint.lng) {
      map.flyTo([selectedComplaint.lat, selectedComplaint.lng], 16, {
        duration: 1.2,
      });
    }
  }, [selectedComplaint, map]);

  // Fit bounds to all coordinates
  useEffect(() => {
    if (shouldFitBounds && complaints.length > 0) {
      const validPoints = complaints
        .filter((c) => c.lat && c.lng)
        .map((c) => [c.lat, c.lng]);

      if (validPoints.length > 0) {
        const bounds = L.latLngBounds(validPoints);
        map.fitBounds(bounds, { padding: [50, 50], maxZoom: 16 });
      }
      onBoundsFitted();
    }
  }, [shouldFitBounds, complaints, map, onBoundsFitted]);

  return null;
}

// Factory for Red Dot Icons
const createRedDotIcon = (severity, urgency, isSelected, isNew) => {
  const isHighOrCritical =
    severity?.toLowerCase() === 'critical' ||
    severity?.toLowerCase() === 'high' ||
    urgency?.toLowerCase() === 'high';

  const size = isSelected ? 22 : isHighOrCritical ? 18 : 14;
  const pulseClass = isHighOrCritical ? 'marker-red-dot-urgent' : 'marker-red-dot';
  const selectedRing = isSelected ? 'ring-4 ring-white/90 scale-125' : '';
  const newAnimation = isNew ? 'animate-bounce' : '';

  return L.divIcon({
    className: 'admin-red-dot-wrapper',
    html: `
      <div class="${pulseClass} ${selectedRing} ${newAnimation}" style="
        width: ${size}px;
        height: ${size}px;
        background-color: #E5484D;
        border: 2px solid #ffffff;
        border-radius: 50%;
        cursor: pointer;
        box-shadow: 0 0 ${isHighOrCritical ? '16px rgba(229,72,77,0.9)' : '10px rgba(229,72,77,0.7)'};
        transition: transform 0.2s ease;
      "></div>
    `,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
};

// Factory for Area Rings (Approximate location without GPS)
const createAreaRingIcon = (isSelected) => {
  return L.divIcon({
    className: 'admin-area-ring-wrapper',
    html: `
      <div class="marker-area-ring ${isSelected ? 'ring-2 ring-white scale-110' : ''}" style="
        width: 24px;
        height: 24px;
        border: 2px dashed #E5484D;
        background: rgba(229, 72, 77, 0.18);
        border-radius: 50%;
        cursor: pointer;
        box-shadow: 0 0 10px rgba(229,72,77,0.4);
      "></div>
    `,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
};

export const AdminMap = ({
  complaints = [],
  selectedComplaint = null,
  onSelectComplaint,
  onRefresh,
  isRefreshing = false,
  newComplaintIds = new Set(),
}) => {
  const [shouldFitBounds, setShouldFitBounds] = useState(false);
  const mapRef = useRef(null);

  // Islamabad / Rawalpindi center coordinates
  const defaultCenter = [33.6444, 73.0645];

  // Count located vs approximate vs unlocated
  const stats = useMemo(() => {
    let exactGps = 0;
    let approximateArea = 0;
    let noLocation = 0;

    complaints.forEach((c) => {
      if (c.lat && c.lng && c.location_source !== 'AreaName') {
        exactGps++;
      } else if (c.lat && c.lng && c.location_source === 'AreaName') {
        approximateArea++;
      } else {
        noLocation++;
      }
    });

    return { exactGps, approximateArea, noLocation };
  }, [complaints]);

  // Initial auto-fit bounds on first load
  useEffect(() => {
    if (complaints.length > 0) {
      setShouldFitBounds(true);
    }
  }, [complaints.length > 0]); // run once when complaints load

  return (
    <div className="relative w-full h-full min-h-[500px] overflow-hidden rounded-3xl border border-white/10 bg-[#030014]">
      {/* Map Container */}
      <MapContainer
        center={defaultCenter}
        zoom={12}
        ref={mapRef}
        scrollWheelZoom={true}
        className="w-full h-full z-0"
      >
        <MapController
          complaints={complaints}
          shouldFitBounds={shouldFitBounds}
          onBoundsFitted={() => setShouldFitBounds(false)}
          selectedComplaint={selectedComplaint}
        />

        {/* Dark Carto Tile Layer */}
        <TileLayer
          attribution='&copy; <a href="https://carto.com/">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          maxZoom={19}
        />

        {/* Located Complaints as RED DOTS */}
        {complaints.map((c) => {
          if (!c.lat || !c.lng) return null;

          const isSelected = selectedComplaint?.id === c.id;
          const isApproximate = c.location_source === 'AreaName';
          const isNew = newComplaintIds.has(c.id);

          const icon = isApproximate
            ? createAreaRingIcon(isSelected)
            : createRedDotIcon(c.severity, c.urgency, isSelected, isNew);

          return (
            <Marker
              key={c.id}
              position={[Number(c.lat), Number(c.lng)]}
              icon={icon}
              eventHandlers={{
                click: () => onSelectComplaint(c),
              }}
            >
              <Popup className="custom-dark-popup">
                <div className="bg-[#0c0c0c] text-white p-2.5 rounded-xl border border-white/10 text-xs min-w-[200px]">
                  <div className="flex items-center justify-between gap-2 mb-1.5 pb-1 border-b border-white/10">
                    <span className="font-bold text-rose-400">
                      {c.item_name || 'Price Violation'}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 font-mono">
                      {c.percentage_overcharge ? `+${Math.round(c.percentage_overcharge)}%` : 'Alert'}
                    </span>
                  </div>
                  <p className="text-white/80 font-medium truncate">
                    {c.shop_name || c.location_area || 'Market Vendor'}
                  </p>
                  <p className="text-[11px] text-white/50 mb-2 truncate">
                    {c.location_area || 'Rawalpindi / Islamabad'}
                  </p>
                  <button
                    onClick={() => onSelectComplaint(c)}
                    className="w-full py-1 text-center bg-rose-600/90 hover:bg-rose-500 text-white rounded text-[11px] font-semibold cursor-pointer transition-colors"
                  >
                    Open Incident Record
                  </button>
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>

      {/* Floating Top Control Bar */}
      <div className="absolute top-4 left-4 right-4 z-[400] flex flex-wrap items-center justify-between gap-3 pointer-events-none">
        {/* Live Counters */}
        <div className="flex items-center gap-2 p-1.5 rounded-2xl bg-black/80 backdrop-blur-xl border border-white/15 pointer-events-auto shadow-xl">
          <div className="flex items-center gap-2 px-3 py-1 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-400 text-xs font-semibold">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500" />
            </span>
            <span>{stats.exactGps} Red Dots</span>
          </div>

          {stats.approximateArea > 0 && (
            <div className="flex items-center gap-1.5 px-2.5 py-1 text-xs text-amber-300 font-medium">
              <span className="w-2.5 h-2.5 rounded-full border border-dashed border-amber-400" />
              <span>{stats.approximateArea} Approx</span>
            </div>
          )}

          {stats.noLocation > 0 && (
            <div className="px-2.5 py-1 text-xs text-white/50 font-medium">
              {stats.noLocation} Unlocated
            </div>
          )}
        </div>

        {/* Map Tool Buttons */}
        <div className="flex items-center gap-2 pointer-events-auto">
          <button
            type="button"
            onClick={() => setShouldFitBounds(true)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-black/80 hover:bg-black/95 text-white/80 hover:text-white border border-white/15 backdrop-blur-xl text-xs font-medium shadow-lg transition-all cursor-pointer"
            title="Fit Map to All Complaints"
          >
            <Maximize2 className="w-3.5 h-3.5 text-rose-400" />
            <span className="hidden sm:inline">Fit All</span>
          </button>

          <button
            type="button"
            onClick={onRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-black/80 hover:bg-black/95 text-white/80 hover:text-white border border-white/15 backdrop-blur-xl text-xs font-medium shadow-lg transition-all cursor-pointer disabled:opacity-50"
            title="Refresh Live Incident Feed"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-violet-400 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>
        </div>
      </div>

      {/* Floating Bottom Legend */}
      <div className="absolute bottom-4 left-4 z-[400] hidden sm:flex items-center gap-4 px-3.5 py-2 rounded-xl bg-black/85 backdrop-blur-xl border border-white/15 text-[11px] text-white/70 shadow-2xl pointer-events-auto">
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-full bg-[#E5484D] border border-white shadow-[0_0_8px_#e5484d]" />
          <span>GPS Red Dot</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3.5 h-3.5 rounded-full border border-dashed border-[#E5484D] bg-[#e5484d]/20" />
          <span>Approx Area</span>
        </div>
        <div className="flex items-center gap-1.5 text-rose-400 font-medium">
          <span className="w-3.5 h-3.5 rounded-full bg-rose-500 animate-pulse border border-white" />
          <span>High Severity / Urgent</span>
        </div>
      </div>
    </div>
  );
};

