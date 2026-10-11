import React, { useState } from 'react';
import { MapContainer, Marker } from 'react-leaflet';
import L from 'leaflet';
import { ExternalLink, MapPin } from 'lucide-react';
import {
  MAP_LAYER_STATUS,
  MapStatusOverlay,
  OpenFreeMapLayer,
} from './OpenFreeMapLayer';

const miniPinIcon = L.divIcon({
  className: 'mini-red-pin',
  html: `
    <div style="position: relative; width: 24px; height: 32px; transform: translate(-12px, -32px);">
      <svg viewBox="0 0 24 24" width="24" height="32" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 0C7.58 0 4 3.58 4 8C4 13.5 12 24 12 24C12 24 20 13.5 20 8C20 3.58 16.42 0 12 0Z" fill="#e5484d" filter="drop-shadow(0 0 6px rgba(229,72,77,0.8))"/>
        <circle cx="12" cy="8" r="3.5" fill="#ffffff"/>
      </svg>
    </div>
  `,
  iconSize: [24, 32],
  iconAnchor: [12, 32],
});

export const MiniLocationMap = ({
  lat,
  lng,
  areaName,
  shopName,
  height = 'h-40',
}) => {
  const [mapStatus, setMapStatus] = useState(MAP_LAYER_STATUS.LOADING);

  if (!lat || !lng) return null;

  const position = [Number(lat), Number(lng)];
  const gmapsUrl = `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;

  return (
    <div className="relative rounded-2xl overflow-hidden border border-white/10 bg-[#080808]">
      <div className={`${height} w-full`}>
        <MapContainer
          center={position}
          zoom={15}
          zoomControl={false}
          dragging={false}
          scrollWheelZoom={false}
          doubleClickZoom={false}
          className="w-full h-full z-0"
        >
          <OpenFreeMapLayer onStatusChange={setMapStatus} />
          <Marker position={position} icon={miniPinIcon} />
        </MapContainer>
      </div>
      <MapStatusOverlay status={mapStatus} className="top-2 left-2" />

      {/* Floating Info Overlay & Google Maps button */}
      <div className="absolute bottom-2 left-2 right-2 z-[400] flex items-center justify-between p-2 rounded-xl bg-black/80 backdrop-blur-md border border-white/10 text-xs">
        <div className="flex items-center gap-1.5 truncate">
          <MapPin className="w-3.5 h-3.5 text-rose-400 shrink-0" />
          <span className="truncate text-white/80 font-medium">
            {shopName ? `${shopName} • ` : ''}{areaName || 'Pinned Location'}
          </span>
        </div>
        <a
          href={gmapsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-[11px] font-semibold text-rose-300 hover:text-white bg-rose-500/20 px-2 py-1 rounded-lg border border-rose-500/30 transition-colors shrink-0"
        >
          <span>Google Maps</span>
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>
    </div>
  );
};

