import React from 'react';
import { Badge } from '../components/ui/Badge';
import { InteractiveMap, SAMPLE_LOCATIONS } from '../components/map/InteractiveMap';

/**
 * HotspotsMapSection
 * Public-facing interactive map of complaint hotspots across the Twin Cities,
 * rendered on OpenStreetMap tiles. Lets citizens browse reported locations,
 * read a short description, search/filter, and recenter.
 */
export const HotspotsMapSection = () => {
  return (
    <section
      id="hotspots-map"
      className="py-24 sm:py-32 relative overflow-hidden bg-[#030014]"
    >
      {/* Ambient background glow */}
      <div className="pointer-events-none absolute top-1/3 left-1/4 w-[600px] h-[400px] bg-rose-900/10 rounded-full blur-[140px]" />

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Header */}
        <div className="flex flex-col items-center text-center mb-10">
          <Badge variant="red" pulsing={true} className="mb-4">
            Complaint Hotspots
          </Badge>
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-extrabold tracking-tight text-white mb-4">
            Explore Reported Locations
          </h2>
          <p className="max-w-2xl text-base sm:text-lg text-white/65">
            Browse where price-gouging, food-safety, and municipal issues are
            being reported across Islamabad and Rawalpindi. Click a pin for
            details, search to jump to a place, or recenter the map.
          </p>
        </div>

        {/* Interactive map */}
        <InteractiveMap locations={SAMPLE_LOCATIONS} height="520px" />
      </div>
    </section>
  );
};
