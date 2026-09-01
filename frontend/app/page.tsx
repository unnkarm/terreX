"use client";

import Header from "@/components/landing/Header";
import Hero from "@/components/landing/Hero";
import InteractiveSimulator from "@/components/landing/InteractiveSimulator";
import CapabilitiesGrid from "@/components/landing/CapabilitiesGrid";
import ArchitectureSection from "@/components/landing/ArchitectureSection";
import TerminalDemo from "@/components/landing/TerminalDemo";
import SpecsComparison from "@/components/landing/SpecsComparison";
import Footer from "@/components/landing/Footer";

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-black text-white font-sans relative overflow-x-hidden selection:bg-white selection:text-black">
      {/* Top Header */}
      <Header />

      {/* Hero Section with 3D Globe */}
      <Hero />

      {/* Interactive Simulator */}
      <InteractiveSimulator />

      {/* Capabilities */}
      <CapabilitiesGrid />

      {/* Architecture & Pipeline */}
      <ArchitectureSection />

      {/* Terminal Demo */}
      <TerminalDemo />

      {/* Specifications */}
      <SpecsComparison />

      {/* Footer */}
      <Footer />
    </main>
  );
}
