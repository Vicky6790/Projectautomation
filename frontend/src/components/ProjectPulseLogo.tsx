import { useEffect, useId, useState } from "react";

const MONOGRAM_PATH = `M 445 495
  L 445 345
  C 445 345, 480 345, 515 345
  C 555 345, 575 365, 575 398
  C 575 432, 552 450, 515 450
  L 480 450
  L 480 495`;

const PULSE_PATH =
  "M 370 420 L 430 420 L 452 380 L 478 465 L 508 360 L 536 450 L 558 405 L 580 420 L 630 420";

type ProjectPulseLogoProps = {
  variant?: "full" | "mark";
  className?: string;
  decorative?: boolean;
};

export function ProjectPulseLogo({
  variant = "full",
  className,
  decorative = false,
}: ProjectPulseLogoProps) {
  const uid = useId().replace(/:/g, "");
  const reducedMotion = usePrefersReducedMotion();
  const markOnly = variant === "mark";
  const ids = {
    spaceBg: `spaceBg-${uid}`,
    neonCyan: `neonCyanGrad-${uid}`,
    orbit1: `orbitGrad1-${uid}`,
    orbit2: `orbitGrad2-${uid}`,
    intenseGlow: `intenseGlow-${uid}`,
    softGlow: `softGlow-${uid}`,
    coreHalo: `coreHalo-${uid}`,
  };

  return (
    <svg
      className={className}
      viewBox="0 0 1000 1000"
      xmlns="http://www.w3.org/2000/svg"
      role={decorative ? undefined : "img"}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : "ProjectPulse"}
    >
      {decorative ? null : <title>ProjectPulse</title>}
      <defs>
        <radialGradient id={ids.spaceBg} cx="50%" cy="45%" r="70%">
          <stop offset="0%" stopColor="#0b1329" />
          <stop offset="50%" stopColor="#070b16" />
          <stop offset="100%" stopColor="#03060c" />
        </radialGradient>
        <linearGradient id={ids.neonCyan} x1="0%" x2="100%" y1="0%" y2="100%">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="50%" stopColor="#06b6d4" />
          <stop offset="100%" stopColor="#3b82f6" />
        </linearGradient>
        <linearGradient id={ids.orbit1} x1="0%" x2="100%" y1="0%" y2="0%">
          <stop offset="0%" stopColor="#38bdf8" stopOpacity="0" />
          <stop offset="40%" stopColor="#06b6d4" stopOpacity="0.8" />
          <stop offset="70%" stopColor="#60a5fa" stopOpacity="1" />
          <stop offset="100%" stopColor="#a855f7" stopOpacity="0" />
        </linearGradient>
        <linearGradient id={ids.orbit2} x1="100%" x2="0%" y1="100%" y2="0%">
          <stop offset="0%" stopColor="#6366f1" stopOpacity="0" />
          <stop offset="50%" stopColor="#38bdf8" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#2dd4bf" stopOpacity="0" />
        </linearGradient>
        <filter id={ids.intenseGlow} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur in="SourceGraphic" result="blur1" stdDeviation="12" />
          <feGaussianBlur in="SourceGraphic" result="blur2" stdDeviation="24" />
          <feGaussianBlur in="SourceGraphic" result="sharp" stdDeviation="4" />
          <feMerge>
            <feMergeNode in="blur2" />
            <feMergeNode in="blur1" />
            <feMergeNode in="sharp" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id={ids.softGlow} x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur in="SourceGraphic" result="blur" stdDeviation="8" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id={ids.coreHalo} x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur result="ambient" stdDeviation="36" />
        </filter>
      </defs>

      <rect fill={`url(#${ids.spaceBg})`} height="1000" rx="140" width="1000" />

      <g
        className={reducedMotion ? undefined : "pp-logo-grid"}
        stroke="#38bdf8"
        strokeOpacity="0.15"
        strokeWidth="1"
      >
        <circle cx="500" cy="420" fill="none" r="320" strokeDasharray="3 9" />
        <circle cx="500" cy="420" fill="none" r="380" strokeDasharray="1 14" />
        <line strokeDasharray="4 8" strokeOpacity="0.2" x1="120" x2="880" y1="420" y2="420" />
        <line strokeDasharray="4 8" strokeOpacity="0.2" x1="500" x2="500" y1="80" y2="760" />
      </g>

      <circle cx="500" cy="420" fill="#0284c7" filter={`url(#${ids.coreHalo})`} opacity="0.2" r="180" />
      <circle cx="500" cy="420" fill="#38bdf8" filter={`url(#${ids.coreHalo})`} opacity="0.25" r="110" />

      <g className={reducedMotion ? undefined : "pp-logo-orbit-ccw"}>
        <circle cx="500" cy="420" fill="none" r="280" stroke="#1e293b" strokeWidth="2.5" />
        <circle
          cx="500"
          cy="420"
          fill="none"
          r="280"
          stroke={`url(#${ids.orbit1})`}
          strokeDasharray="120 440"
          strokeLinecap="round"
          strokeWidth="4"
        />
        <circle
          cx="500"
          cy="420"
          fill="none"
          r="280"
          stroke="#38bdf8"
          strokeDasharray="50 700"
          strokeLinecap="round"
          strokeWidth="3"
        />
        <g transform="translate(500, 140)">
          <circle fill="#0f172a" filter={`url(#${ids.softGlow})`} r="9" stroke="#38bdf8" strokeWidth="3" />
          <circle fill="#38bdf8" r="4" />
          <circle fill="none" opacity="0.6" r="16" stroke="#38bdf8" strokeDasharray="2 4" strokeWidth="1" />
        </g>
        <g transform="translate(500, 700)">
          <circle fill="#818cf8" filter={`url(#${ids.softGlow})`} r="6" />
        </g>
      </g>

      <g className={reducedMotion ? undefined : "pp-logo-orbit-cw"}>
        <ellipse
          cx="500"
          cy="420"
          fill="none"
          opacity="0.4"
          rx="220"
          ry="200"
          stroke="#334155"
          strokeDasharray="8 12"
          strokeWidth="2"
        />
        <ellipse
          cx="500"
          cy="420"
          fill="none"
          filter={`url(#${ids.softGlow})`}
          rx="220"
          ry="200"
          stroke={`url(#${ids.orbit2})`}
          strokeDasharray="90 320"
          strokeLinecap="round"
          strokeWidth="4.5"
        />
        <g transform="translate(720, 420)">
          <circle fill="#22d3ee" filter={`url(#${ids.intenseGlow})`} r="8" />
          <circle fill="#ffffff" r="3" />
        </g>
        <g transform="translate(280, 420)">
          <circle fill="#a855f7" filter={`url(#${ids.softGlow})`} r="5" />
        </g>
      </g>

      <g className={reducedMotion ? undefined : "pp-logo-orbit-fast"}>
        <circle
          cx="500"
          cy="420"
          fill="none"
          filter={`url(#${ids.softGlow})`}
          opacity="0.7"
          r="160"
          stroke="#0ea5e9"
          strokeDasharray="20 180"
          strokeWidth="2"
        />
      </g>

      <g className={reducedMotion ? undefined : "pp-logo-pulse-core"}>
        <circle cx="500" cy="420" fill="#090e1a" r="125" stroke="#1e293b" strokeWidth="4" />
        <circle
          cx="500"
          cy="420"
          fill="none"
          opacity="0.8"
          r="120"
          stroke={`url(#${ids.neonCyan})`}
          strokeWidth="3"
        />
        <path
          d={MONOGRAM_PATH}
          fill="none"
          stroke="#0f213d"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="32"
        />
        <path
          d={MONOGRAM_PATH}
          fill="none"
          filter={`url(#${ids.softGlow})`}
          stroke={`url(#${ids.neonCyan})`}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="18"
        />
        <path
          d={MONOGRAM_PATH}
          fill="none"
          stroke="#f0f9ff"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="6"
        />
        <path
          d={PULSE_PATH}
          fill="none"
          stroke="#0b1e38"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="12"
        />
        <path
          d={PULSE_PATH}
          fill="none"
          filter={`url(#${ids.intenseGlow})`}
          stroke="#38bdf8"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="7"
        >
          {reducedMotion ? null : (
            <>
              <animate
                attributeName="stroke-dasharray"
                dur="2.4s"
                repeatCount="indefinite"
                values="60 260; 120 180; 60 260"
              />
              <animate
                attributeName="stroke-dashoffset"
                dur="2.4s"
                repeatCount="indefinite"
                values="320; 0; -320"
              />
            </>
          )}
        </path>
        <path
          d={PULSE_PATH}
          fill="none"
          stroke="#ffffff"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="3"
        >
          {reducedMotion ? null : (
            <>
              <animate
                attributeName="stroke-dasharray"
                dur="2.4s"
                repeatCount="indefinite"
                values="40 280; 90 230; 40 280"
              />
              <animate
                attributeName="stroke-dashoffset"
                dur="2.4s"
                repeatCount="indefinite"
                values="320; 0; -320"
              />
            </>
          )}
        </path>
        <circle cx="508" cy="360" fill="#ffffff" filter={`url(#${ids.intenseGlow})`} r="5">
          {reducedMotion ? null : (
            <animate attributeName="opacity" dur="1.2s" repeatCount="indefinite" values="0.3;1;0.3" />
          )}
        </circle>
      </g>

      {markOnly ? null : (
        <g
          fontFamily="system-ui, -apple-system, 'SF Pro Display', 'Hanken Grotesk', sans-serif"
          textAnchor="middle"
        >
          <g transform="translate(500, 640)">
            <rect
              fill="#0d1829"
              height="36"
              rx="18"
              stroke="#1e293b"
              strokeWidth="1.5"
              width="220"
              x="-110"
              y="-18"
            />
            <circle cx="-78" cy="0" fill="#10b981" r="5">
              {reducedMotion ? null : (
                <animate attributeName="opacity" dur="2s" repeatCount="indefinite" values="1;0.4;1" />
              )}
            </circle>
            <text fill="#38bdf8" fontSize="12" fontWeight="700" letterSpacing="3" x="12" y="5">
              TELEMETRY ACTIVE
            </text>
          </g>
          <g transform="translate(500, 750)">
            <text
              fill="#38bdf8"
              filter={`url(#${ids.intenseGlow})`}
              fontSize="68"
              fontWeight="800"
              letterSpacing="3"
              opacity="0.35"
              x="0"
              y="0"
            >
              ProjectPulse
            </text>
            <text fill="#ffffff" fontSize="68" fontWeight="800" letterSpacing="3" x="0" y="0">
              Project
              <tspan fill="#38bdf8">Pulse</tspan>
            </text>
          </g>
          <text fill="#94a3b8" fontSize="15" fontWeight="600" letterSpacing="4.5" x="500" y="805">
            PROJECT INTELLIGENCE PLATFORM
          </text>
          <g fill="#475569" fontSize="11" fontWeight="600" letterSpacing="2" transform="translate(500, 860)">
            <text x="-160" y="0">
              SYNC FREQ · 60HZ
            </text>
            <circle cx="-50" cy="-3" fill="#334155" r="2.5" />
            <text x="0" y="0">
              LATENCY · 0MS
            </text>
            <circle cx="50" cy="-3" fill="#334155" r="2.5" />
            <text x="160" y="0">
              CORE · NEURAL V3
            </text>
          </g>
        </g>
      )}
    </svg>
  );
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return reduced;
}
