type Props = {
  value: number | null | undefined;
};

export function WsrProgressRing({ value }: Props) {
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const ready = value !== null && value !== undefined;
  const pct = ready ? Math.min(100, Math.max(0, value)) : 0;
  const dash = (pct / 100) * circumference;
  return (
    <div className="progress-ring">
      <svg viewBox="0 0 128 128" aria-hidden="true">
        <circle className="ring-track" cx="64" cy="64" r={radius} />
        <circle
          className="ring-value"
          cx="64"
          cy="64"
          r={radius}
          strokeDasharray={`${dash} ${circumference}`}
          transform="rotate(-90 64 64)"
        />
      </svg>
      <div className="ring-label">
        <strong>{ready ? `${Math.round(pct)}%` : "—"}</strong>
        <span>Overall Progress</span>
      </div>
    </div>
  );
}
