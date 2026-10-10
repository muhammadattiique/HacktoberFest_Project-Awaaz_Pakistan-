import React, { useEffect } from 'react';
import { useMap } from 'react-leaflet';
import { setWorkerUrl } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { maplibreGL } from '@maplibre/maplibre-gl-leaflet';

const OPEN_FREE_MAP_STYLE = 'https://tiles.openfreemap.org/styles/dark';

setWorkerUrl(workerUrl);

export const MAP_LAYER_STATUS = {
  LOADING: 'loading',
  READY: 'ready',
  ERROR: 'error',
};

export const OpenFreeMapLayer = ({ onStatusChange }) => {
  const map = useMap();

  useEffect(() => {
    let layer;
    let maplibreMap;

    const handleLoad = () => onStatusChange(MAP_LAYER_STATUS.READY);
    const handleError = () => onStatusChange(MAP_LAYER_STATUS.ERROR);

    onStatusChange(MAP_LAYER_STATUS.LOADING);

    try {
      layer = maplibreGL({
        style: OPEN_FREE_MAP_STYLE,
      }).addTo(map);
      maplibreMap = layer.getMaplibreMap();
      maplibreMap.on('load', handleLoad);
      maplibreMap.on('error', handleError);
    } catch (error) {
      console.error('Unable to initialize OpenFreeMap:', error);
      handleError();
    }

    return () => {
      if (maplibreMap) {
        maplibreMap.off('load', handleLoad);
        maplibreMap.off('error', handleError);
      }
      if (layer && map.hasLayer(layer)) {
        map.removeLayer(layer);
      }
    };
  }, [map, onStatusChange]);

  return null;
};

export const MapStatusOverlay = ({ status, className = 'top-2 right-2' }) => {
  if (status === MAP_LAYER_STATUS.READY) return null;

  return (
    <div
      role={status === MAP_LAYER_STATUS.ERROR ? 'alert' : 'status'}
      className={`absolute ${className} z-[450] max-w-64 rounded-lg border px-2.5 py-1.5 text-[11px] leading-snug shadow-lg backdrop-blur-md pointer-events-none ${
        status === MAP_LAYER_STATUS.ERROR
          ? 'border-amber-500/30 bg-black/90 text-amber-200'
          : 'border-white/10 bg-black/75 text-white/70'
      }`}
    >
      {status === MAP_LAYER_STATUS.ERROR
        ? 'Map unavailable. Check your connection and reload; pins and controls still work.'
        : 'Loading map…'}
    </div>
  );
};
