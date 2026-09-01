"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import Logo from "@/components/Logo";

export default function Header() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-50 transition-colors duration-300 ${
        scrolled ? "bg-black/90 backdrop-blur-sm border-b border-white/10 py-4" : "bg-transparent py-6"
      }`}
    >
      <div className="max-w-7xl mx-auto px-6 sm:px-8 flex items-center justify-between">
        
        {/* Brand / Logo (Faithful to uploaded logo lockup) */}
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-4 group">
            {/* The exact TerreX Logo */}
            <Logo size={40} showText={true} />

            {/* Subtitle tag from reference image */}
            <span className="hidden md:inline-block text-[10px] tracking-widest text-neutral-500 uppercase font-sans font-medium border-l border-neutral-800 pl-4 py-0.5">
              ISRO GEOSPATIAL INTELLIGENCE PORTAL
            </span>
          </Link>
        </div>

        {/* Minimal Navigation Links (Inter / sans font) */}
        <div className="hidden md:flex items-center gap-9">
          <nav className="flex items-center gap-8 text-[11px] font-sans tracking-widest uppercase text-neutral-400 font-medium">
            <a href="#technology" className="hover:text-white transition duration-150">
              TECHNOLOGY
            </a>
            <a href="#simulator" className="hover:text-white transition duration-150">
              SIMULATOR
            </a>
            <a href="#specs" className="hover:text-white transition duration-150">
              ISRO SPEC
            </a>
          </nav>

          {/* Launch Console Button (Thin outline box matching reference image) */}
          <Link
            href="/workspace"
            className="px-5 py-2 text-white font-sans text-xs tracking-widest uppercase border border-white/80 hover:bg-white hover:text-black transition duration-150"
          >
            LAUNCH CONSOLE
          </Link>
        </div>

        {/* Mobile menu toggle */}
        <div className="md:hidden flex items-center gap-3">
          <Link
            href="/workspace"
            className="px-3 py-1.5 text-white font-sans text-[11px] tracking-widest uppercase border border-white/70"
          >
            LAUNCH
          </Link>
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-1.5 text-neutral-400 hover:text-white"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {mobileMenuOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>
        </div>
      </div>

      {/* Mobile Dropdown */}
      {mobileMenuOpen && (
        <div className="md:hidden bg-black border-b border-neutral-800 px-6 pt-4 pb-6 space-y-4 font-sans text-xs tracking-widest uppercase">
          <a
            href="#technology"
            onClick={() => setMobileMenuOpen(false)}
            className="block text-neutral-300 hover:text-white"
          >
            TECHNOLOGY
          </a>
          <a
            href="#simulator"
            onClick={() => setMobileMenuOpen(false)}
            className="block text-neutral-300 hover:text-white"
          >
            SIMULATOR
          </a>
          <a
            href="#specs"
            onClick={() => setMobileMenuOpen(false)}
            className="block text-neutral-300 hover:text-white"
          >
            ISRO SPEC
          </a>
          <div className="pt-2 border-t border-neutral-800">
            <Link
              href="/workspace"
              onClick={() => setMobileMenuOpen(false)}
              className="block w-full text-center py-2.5 bg-white text-black font-semibold text-xs"
            >
              LAUNCH CONSOLE
            </Link>
          </div>
        </div>
      )}
    </header>
  );
}
