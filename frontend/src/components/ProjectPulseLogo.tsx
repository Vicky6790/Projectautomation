import { useEffect, useId, useState } from "react";

const MONOGRAM_PATH = `M 220 200
  L 520 200
  A 180 180 0 0 1 700 380
  A 180 180 0 0 1 520 560
  L 360 560
  L 360 820
  L 220 820
  Z`;

const PULSE_PATH =
  "M 390 380 L 440 380 L 470 320 L 510 460 L 550 300 L 590 420 L 620 380 L 670 380";

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
    bg: `bgGrad-${uid}`,
    glow: `glow-${uid}`,
    pulse: `pulseGrad-${uid}`,
  };

  return (
    <svg
      className={className}
      viewBox="0 0 1024 1024"
      xmlns="http://www.w3.org/2000/svg"
      role={decorative ? undefined : "img"}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : "ProjectPulse"}
    >
      {decorative ? null : <title>ProjectPulse</title>}
      <defs>
        <radialGradient id={ids.bg} cx="50%" cy="50%" r="70%">
          <stop offset="0%" stopColor="#1e293b" />
          <stop offset="100%" stopColor="#0f172a" />
        </radialGradient>
        <filter id={ids.glow} x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur result="blur" stdDeviation="12" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
        <linearGradient id={ids.pulse} x1="0%" x2="100%" y1="0%" y2="0%">
          <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.3" />
          <stop offset="50%" stopColor="#38bdf8" stopOpacity="1" />
          <stop offset="100%" stopColor="#22d3ee" stopOpacity="0.3" />
        </linearGradient>
      </defs>
      <rect fill={`url(#${ids.bg})`} height="1024" rx="200" width="1024" />
      <g transform="translate(0, 40)">
        <path
          d={MONOGRAM_PATH}
          fill="none"
          opacity="0.15"
          stroke="#38bdf8"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="36"
        />
        <path
          d={MONOGRAM_PATH}
          fill="none"
          stroke="#f8fafc"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="32"
        >
          {reducedMotion ? null : (
            <>
              <animate attributeName="stroke-dasharray" dur="3s" repeatCount="indefinite" values="2500;2500" />
              <animate
                attributeName="stroke-dashoffset"
                calcMode="spline"
                dur="3s"
                keySplines="0.4 0 0.2 1"
                keyTimes="0;1"
                repeatCount="indefinite"
                values="2500;0"
              />
            </>
          )}
        </path>
        <circle cx="520" cy="380" fill="#0f172a" r="140" stroke="#1e293b" strokeWidth="8" />
        <path
          d={PULSE_PATH}
          fill="none"
          filter={`url(#${ids.glow})`}
          stroke={`url(#${ids.pulse})`}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="12"
        >
          {reducedMotion ? null : (
            <animate attributeName="opacity" dur="2s" repeatCount="indefinite" values="0.6;1;0.6" />
          )}
        </path>
        {reducedMotion ? (
          <circle cx="550" cy="300" fill="#ffffff" filter={`url(#${ids.glow})`} r="8" />
        ) : (
          <circle fill="#ffffff" filter={`url(#${ids.glow})`} r="8">
            <animateMotion dur="2s" path={PULSE_PATH} repeatCount="indefinite" />
            <animate attributeName="opacity" dur="2s" repeatCount="indefinite" values="0;1;1;0" />
          </circle>
        )}
        {markOnly ? null : (
          <g textAnchor="middle" transform="translate(512, 730)">
            <text
              fill="#22d3ee"
              filter={`url(#${ids.glow})`}
              fontFamily="Hanken Grotesk, system-ui, -apple-system, sans-serif"
              fontSize="76"
              fontWeight="800"
              opacity="0.3"
              x="0"
              y="0"
            >
              ProjectPulse
            </text>
            <text
              fill="#ffffff"
              fontFamily="Hanken Grotesk, system-ui, -apple-system, sans-serif"
              fontSize="76"
              fontWeight="800"
              letterSpacing="1"
              x="0"
              y="0"
            >
              Project
              <tspan fill="#22d3ee">Pulse</tspan>
            </text>
          </g>
        )}
      </g>
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
