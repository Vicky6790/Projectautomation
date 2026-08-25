import type { PhaseStatus } from "../types";

const COLORS = ["#1f9d6a", "#3b82f6", "#4338ca", "#f59e0b", "#0ea5e9", "#8b5cf6", "#db2777"];

function parseDay(value?: string | null): Date | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function monthsBetween(start: Date, end: Date): Date[] {
  const months: Date[] = [];
  const cursor = new Date(start.getFullYear(), start.getMonth(), 1);
  const last = new Date(end.getFullYear(), end.getMonth(), 1);
  while (cursor <= last) {
    months.push(new Date(cursor));
    cursor.setMonth(cursor.getMonth() + 1);
  }
  return months.length ? months : [start];
}

type Props = {
  phases: PhaseStatus[];
  asOf?: string | null;
};

export function WsrGantt({ phases, asOf }: Props) {
  const dated = phases
    .map((phase) => ({
      ...phase,
      start: parseDay(phase.planned_start),
      finish: parseDay(phase.planned_finish),
    }))
    .filter((phase) => phase.start || phase.finish);
  if (!dated.length) {
    return <p className="muted">A timeline cannot be generated</p>;
  }
  const starts = dated.map((phase) => (phase.start ?? phase.finish) as Date);
  const ends = dated.map((phase) => (phase.finish ?? phase.start) as Date);
  const min = new Date(Math.min(...starts.map((item) => item.getTime())));
  const max = new Date(Math.max(...ends.map((item) => item.getTime())));
  const span = Math.max(max.getTime() - min.getTime(), 1);
  const ticks = monthsBetween(min, max);
  const today = parseDay(asOf);
  const todayLeft =
    today && today.getTime() >= min.getTime() && today.getTime() <= max.getTime()
      ? ((today.getTime() - min.getTime()) / span) * 100
      : null;

  return (
    <div className="gantt">
      <div className="gantt-head">
        <span className="gantt-label" />
        <div className="gantt-track gantt-months">
          {ticks.map((month) => {
            const left = ((month.getTime() - min.getTime()) / span) * 100;
            return (
              <span key={month.toISOString()} style={{ left: `${Math.max(left, 0)}%` }}>
                {month.toLocaleDateString("en-GB", { month: "short", year: "2-digit" })}
              </span>
            );
          })}
        </div>
      </div>
      {dated.map((phase, index) => {
        const start = (phase.start ?? phase.finish) as Date;
        const finish = (phase.finish ?? phase.start) as Date;
        const left = ((start.getTime() - min.getTime()) / span) * 100;
        const width = Math.max(((finish.getTime() - start.getTime()) / span) * 100, 1.5);
        return (
          <div className="gantt-row" key={phase.name}>
            <span className="gantt-label">{phase.name}</span>
            <div className="gantt-track">
              {todayLeft !== null ? <span className="gantt-today" style={{ left: `${todayLeft}%` }} /> : null}
              <span
                className="gantt-bar"
                style={{
                  left: `${left}%`,
                  width: `${width}%`,
                  background: COLORS[index % COLORS.length],
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
