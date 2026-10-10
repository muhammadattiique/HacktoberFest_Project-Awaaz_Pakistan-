import React from 'react';
import { useSmoothScroll } from '../hooks/useSmoothScroll';
import { useAvatarState } from '../hooks/useAvatarState';
import { Navbar } from '../components/ui/Navbar';
import { Footer } from '../components/ui/Footer';
import { HeroSection } from '../sections/HeroSection';
import { LiveTicker } from '../sections/LiveTicker';
import { HowItWorksSection } from '../sections/HowItWorksSection';
import { KeyFeaturesSection } from '../sections/KeyFeaturesSection';
import { ReportSection } from '../sections/ReportSection';
import { LiveImpactStatsSection } from '../sections/LiveImpactStatsSection';
import { RecentComplaintsSection } from '../sections/RecentComplaintsSection';
import { OfficialRatesSection } from '../sections/OfficialRatesSection';
import { FaqSection } from '../sections/FaqSection';
import { FinalCtaSection } from '../sections/FinalCtaSection';

export const Home = () => {
  // Initialize Lenis smooth scroll
  useSmoothScroll();

  // Shared 3D Avatar state machine
  const avatarController = useAvatarState();

  return (
    <div className="min-h-screen bg-[#030014] text-white selection:bg-[#814bee]/30 selection:text-white relative">
      {/* Sticky Glass Navbar */}
      <Navbar />

      <main>
        {/* 1. Hero Section with 3D Avatar */}
        <HeroSection
          avatarState={avatarController.avatarState}
          stepLabel={avatarController.stepLabel}
          floatingChips={avatarController.floatingChips}
        />

        {/* 2. Live Ticker */}
        <LiveTicker />

        {/* 3. How It Works */}
        <HowItWorksSection />

        {/* 4. Key Features */}
        <KeyFeaturesSection />

        {/* 5. Report (Visual & Functional Centerpiece) */}
        <ReportSection
          avatarController={avatarController}
        />

        {/* 6. Live Impact Stats & Chart */}
        <LiveImpactStatsSection />

        {/* 7. Recent Complaints Feed */}
        <RecentComplaintsSection />

        {/* 8. Official Rates Directory */}
        <OfficialRatesSection />

        {/* 9. FAQ with Location Pin Explanation */}
        <FaqSection />

        {/* 10. Final CTA Banner */}
        <FinalCtaSection />
      </main>

      {/* Minimal Footer */}
      <Footer />
    </div>
  );
};

