"use client";

import React from "react";

interface LogoProps {
  className?: string;
  size?: number;
  showText?: boolean;
  variant?: "full" | "icon" | "stacked";
}

export default function Logo({
  className = "",
  size = 38,
  showText = true,
  variant = "full",
}: LogoProps) {
  // If variant is "stacked", show the complete vertical lockup (Globe + Satellite on top, TerreX below)
  if (variant === "stacked") {
    return (
      <div className={`inline-flex flex-col items-center select-none ${className}`}>
        {/* Globe + Satellite Icon */}
        <LogoIcon size={size * 1.5} />
        {/* Wordmark */}
        <div className="flex items-baseline font-sans font-black tracking-tight mt-1">
          <span className="text-white text-2xl font-bold tracking-tight">Terre</span>
          <span className="text-2xl font-extrabold bg-gradient-to-tr from-[#0080ff] via-[#00c0ff] to-[#22c55e] bg-clip-text text-transparent">
            X
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className={`inline-flex items-center gap-2.5 select-none ${className}`}>
      {/* Globe + Satellite Icon */}
      <LogoIcon size={size} />

      {/* TerreX Wordmark */}
      {showText && (
        <div className="flex items-baseline font-sans font-black tracking-tight leading-none">
          <span
            className="text-white font-bold tracking-tight"
            style={{ fontSize: `${Math.max(16, size * 0.54)}px` }}
          >
            Terre
          </span>
          <span
            className="font-black bg-gradient-to-tr from-[#0080ff] via-[#00c8ff] to-[#22c55e] bg-clip-text text-transparent"
            style={{
              fontSize: `${Math.max(17, size * 0.58)}px`,
              marginLeft: "0.5px",
            }}
          >
            X
          </span>
        </div>
      )}
    </div>
  );
}

export function LogoIcon({ size = 38 }: { size?: number }) {
  return (
    <div
      className="relative flex-shrink-0"
      style={{ width: size, height: size }}
    >
      <svg
        viewBox="0 0 200 200"
        className="w-full h-full"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          {/* Earth Ocean Gradient (Vibrant Blue to Deep Blue) */}
          <radialGradient id="earthRadial" cx="38%" cy="32%" r="68%">
            <stop offset="0%" stopColor="#3b82f6" />
            <stop offset="45%" stopColor="#1d4ed8" />
            <stop offset="90%" stopColor="#1e3a8a" />
            <stop offset="100%" stopColor="#0f172a" />
          </radialGradient>

          {/* Radar Scan Beam Cone */}
          <linearGradient id="radarScanCone" x1="146" y1="48" x2="98" y2="95" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.95" />
            <stop offset="65%" stopColor="#0ea5e9" stopOpacity="0.65" />
            <stop offset="100%" stopColor="#0284c7" stopOpacity="0.35" />
          </linearGradient>

          {/* Blue Swoop Orbit */}
          <linearGradient id="blueOrbitRing" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#00d2ff" />
            <stop offset="100%" stopColor="#0066ff" />
          </linearGradient>
        </defs>

        {/* Outer White Orbit Ring */}
        <path
          d="M 46 102 C 40 58, 122 36, 156 78 C 172 98, 152 134, 102 144 C 72 150, 48 134, 46 102 Z"
          stroke="#ffffff"
          strokeWidth="6"
          strokeLinecap="round"
          fill="none"
        />

        {/* Lower Cyan Swoosh Orbit Ring */}
        <path
          d="M 48 116 C 52 144, 98 154, 142 126 C 170 108, 178 84, 164 70"
          stroke="url(#blueOrbitRing)"
          strokeWidth="6.5"
          strokeLinecap="round"
          fill="none"
        />

        {/* Earth Globe Sphere */}
        <circle cx="98" cy="95" r="46" fill="url(#earthRadial)" />

        {/* Continents (Vibrant Green) */}
        <g fill="#22c55e">
          {/* North America */}
          <path d="M 80 70 Q 88 64 98 66 Q 106 70 102 80 Q 94 84 86 80 Q 78 78 80 70 Z" />
          <path d="M 74 74 Q 82 76 80 86 Q 72 84 74 74 Z" />
          {/* South America */}
          <path d="M 86 86 Q 94 90 92 104 Q 96 118 88 128 Q 82 124 84 108 Q 80 96 86 86 Z" />
          {/* Europe / Africa edge */}
          <path d="M 120 70 Q 130 66 134 76 Q 128 84 122 82 Z" />
          <path d="M 124 86 Q 136 92 132 110 Q 122 116 120 100 Q 120 90 124 86 Z" />
        </g>

        {/* Earth Atmospheric Rim Highlight */}
        <circle
          cx="98"
          cy="95"
          r="46"
          stroke="rgba(255, 255, 255, 0.45)"
          strokeWidth="1.8"
          fill="none"
        />

        {/* Radar Beam Cone from Satellite */}
        <polygon
          points="146,48 98,80 134,104"
          fill="url(#radarScanCone)"
        />

        {/* Satellite at Top-Right (45 deg tilt) */}
        <g transform="translate(146, 48) rotate(-42)">
          {/* Left Solar Panel */}
          <rect x="-30" y="-8" width="18" height="16" rx="2" fill="#ffffff" stroke="#000000" strokeWidth="1.5" />
          <line x1="-21" y1="-8" x2="-21" y2="8" stroke="#000000" strokeWidth="1" />
          <line x1="-30" y1="0" x2="-12" y2="0" stroke="#000000" strokeWidth="1" />
          
          {/* Connector Left */}
          <line x1="-12" y1="0" x2="-8" y2="0" stroke="#ffffff" strokeWidth="2.5" />

          {/* Central Body */}
          <rect x="-8" y="-7" width="16" height="14" rx="2" fill="#ffffff" stroke="#000000" strokeWidth="1.5" />
          <circle cx="0" cy="0" r="3" fill="#0284c7" />

          {/* Connector Right */}
          <line x1="8" y1="0" x2="12" y2="0" stroke="#ffffff" strokeWidth="2.5" />

          {/* Right Solar Panel */}
          <rect x="12" y="-8" width="18" height="16" rx="2" fill="#ffffff" stroke="#000000" strokeWidth="1.5" />
          <line x1="21" y1="-8" x2="21" y2="8" stroke="#000000" strokeWidth="1" />
          <line x1="12" y1="0" x2="30" y2="0" stroke="#000000" strokeWidth="1" />

          {/* Sensor Aperture Lens */}
          <path d="M -4 7 L 4 7 L 2 11 L -2 11 Z" fill="#00d2ff" />
        </g>
      </svg>
    </div>
  );
}
