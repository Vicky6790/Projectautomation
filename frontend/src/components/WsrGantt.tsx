import type { PhaseStatus } from "../types";
import { durationDays, phaseWbs, windowRange } from "../wsrFormat";

const COLORS = ["#475569", "#6366f1", "#6366f1", "#10b981", "#10b981", "#8b5cf6", "#8b5cf6", "#f59e0b"];

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
  return months.length ? months : [new Date(start.getFullYear(), start.getMonth(), 1)];
}

function dateToPercent(value: Date, months: Date[]): number {
  const first = months[0];
  const index = (value.getFullYear() - first.getFullYear()) * 12 + (value.getMonth() - first.getMonth());
  const daysInMonth = new Date(value.getFullYear(), value.getMonth() + 1, 0).getDate();
  const fraction = (value.getDate() - 1) / daysInMonth;
  return ((Math.max(index, 0) + fraction) / months.length) * 100;
}

type Props = {
  phases: PhaseStatus[];
  asOf?: string | null;
};

export function WsrGantt({ phases, asOf }: Props) {
  const rows = phases.map((phase, index) => {
    const startValue = phase.planned_start || phase.actual_start;
    const finishValue = phase.planned_finish || phase.actual_finish;
    return {
      ...phase,
      wbs: phaseWbs(phase, index),
      startValue,
      finishValue,
      start: parseDay(startValue),
      finish: parseDay(finishValue),
    };
  });
  const dated = rows.filter((phase) => phase.start || phase.finish);
  if (!dated.length) {
    return <p className="muted">A timeline cannot be generated</p>;
  }
  const starts = dated.map((phase) => (phase.start ?? phase.finish) as Date);
  const ends = dated.map((phase) => (phase.finish ?? phase.start) as Date);
  const min = new Date(Math.min(...starts.map((item) => item.getTime())));
  const max = new Date(Math.max(...ends.map((item) => item.getTime())));
  const months = monthsBetween(min, max);
  const today = parseDay(asOf);
  const todayLeft =
    today && today.getTime() >= min.getTime() && today.getTime() <= max.getTime()
      ? dateToPercent(today, months)
      : null;
  const todayMonth =
    today &&
    months.findIndex(
      (month) => month.getFullYear() === today.getFullYear() && month.getMonth() === today.getMonth(),
    );

  return (
    <div className="gantt-exec">
      <div className="gantt-exec-inner">
        <div className="gantt-row-exec gantt-head-exec">
          <div>Phase</div>
          <div>Window · Dur</div>
          <div />
          <div className="gantt-months-exec" style={{ gridTemplateColumns: `repeat(${months.length}, 1fr)` }}>
            {months.map((month, index) => (
              <span
                key={month.toISOString()}
                className={index === todayMonth ? "gantt-month-today" : undefined}
              >
                {month.toLocaleDateString("en-GB", { month: "short", year: "numeric" })}
                {index === todayMonth ? <em>Today</em> : null}
              </span>
            ))}
          </div>
        </div>
        <div className="gantt-body-exec" style={{ ["--gantt-months" as string]: months.length }}>
          {rows.map((phase, index) => {
            const start = phase.start ?? phase.finish;
            const finish = phase.finish ?? phase.start;
            const left = start ? dateToPercent(start, months) : null;
            const right = finish ? dateToPercent(finish, months) : null;
            const width = left != null && right != null ? Math.max(right - left, 1.5) : 0;
            const days = durationDays(phase.startValue, phase.finishValue);
            const showLabel = width >= 12;
            return (
              <div className="gantt-row-exec" key={`${phase.wbs}-${phase.name}`}>
                <div className="gantt-phase-exec">
                  <span className="gantt-wbs">{phase.wbs}</span>
                  <span className="gantt-name">{phase.name}</span>
                </div>
                <div className="gantt-window-exec">
                  {phase.start || phase.finish
                    ? windowRange(phase.startValue, phase.finishValue, "arrow")
                    : "—"}
                </div>
                <div className="gantt-dur-exec">{days != null ? `${days}d` : "—"}</div>
                <div className="gantt-track-exec">
                  {todayLeft !== null ? (
                    <span className="gantt-today-exec" style={{ left: `${todayLeft}%` }} aria-hidden="true" />
                  ) : null}
                  {left != null && width > 0 ? (
                    <span
                      className="gantt-bar-exec"
                      style={{
                        left: `${left}%`,
                        width: `${width}%`,
                        background: COLORS[index % COLORS.length],
                      }}
                      title={`${phase.name}: ${windowRange(phase.startValue, phase.finishValue, "dash")}`}
                    >
                      {showLabel ? phase.name : ""}
                    </span>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
