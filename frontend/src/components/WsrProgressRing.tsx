type Props = {
  value: number | null | undefined;
  size?: "sm" | "lg";
};

export function WsrProgressRing({ value, size = "sm" }: Props) {
  const ready = value !== null && value !== undefined;
  const pct = ready ? Math.min(100, Math.max(0, value)) : 0;
  const radius = 16;
  const circumference = 2 * Math.PI * radius;
  const dash = (pct / 100) * circumference;
  return (
    <div className={`progress-ring progress-ring-${size}`}>
      <svg viewBox="0 0 36 36" aria-hidden="true">
        <circle className="ring-track" cx="18" cy="18" r={radius} />
        <circle
          className="ring-value"
          cx="18"
          cy="18"
          r={radius}
          strokeDasharray={`${dash} ${circumference}`}
          transform="rotate(-90 18 18)"
        />
      </svg>
      <span className="ring-pct">{ready ? `${Math.round(pct)}%` : "—"}</span>
    </div>
  );
}
