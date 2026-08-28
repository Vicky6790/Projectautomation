import { useContext, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getWsrRequest } from "./api";
import { ShellMetaContext } from "./shellMeta";
import type { DelayMappingRow, DelayMappingSheet, WsrPlanFacts } from "./types";
import { compactDate, unavailable, windowRange } from "./wsrFormat";
import { asWsrReport, readWsrSession } from "./wsrSession";

export function DelayMappingView() {
  const setPageMeta = useContext(ShellMetaContext);
  const session = readWsrSession();
  const handle = session?.handle ?? null;
  const [message, setMessage] = useState(
    session ? "Loading delay mapping from the generated WSR…" : "Generate a WSR to open the Delay Mapping Sheet.",
  );
  const [facts, setFacts] = useState<WsrPlanFacts | null>(null);

  useEffect(() => {
    if (!handle) {
      return;
    }
    let cancelled = false;
    getWsrRequest(handle)
      .then((job) => {
        if (cancelled) {
          return;
        }
        const report = asWsrReport(job.result ?? null);
        if (job.status !== "succeeded" || !report?.facts) {
          setMessage("Generate a WSR to open the Delay Mapping Sheet.");
          return;
        }
        setFacts(report.facts);
        setMessage("");
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setMessage(error instanceof Error ? error.message : "Could not load the generated WSR.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [handle]);

  useEffect(() => {
    const identity = [facts?.project_name, facts?.project_owner].filter(Boolean).join(" · ");
    setPageMeta(identity);
    return () => setPageMeta("");
  }, [facts?.project_name, facts?.project_owner, setPageMeta]);

  const mapping: DelayMappingSheet = facts?.delay_mapping ?? { total_delayed_days: 0, delayed_task_count: 0, rows: [] };
  const rows = mapping.rows ?? [];
  const delayedDays = mapping.total_delayed_days ?? 0;
  const delayedTasks = mapping.delayed_task_count ?? 0;
  const project = facts?.project_name?.trim();
  const intro = project
    ? `Schedule variances and delayed work from the uploaded plan for ${project}.`
    : "Schedule variances and delayed work from the uploaded plan.";

  if (!facts) {
    return (
      <section className="delay-page">
        <div className="delay-empty">
          <h2>Delay Mapping Sheet</h2>
          <p>{message}</p>
          <Link className="btn btn-primary" to="/wsr">
            Back to WSR & Insights
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section className="delay-page">
      <div className="delay-head">
        <div>
          <div className="delay-crumb">
            <Link to="/wsr">WSR & Insights</Link>
            <span className="material-symbols-outlined" aria-hidden="true">
              chevron_right
            </span>
            <span>Risk Management</span>
            <span className="material-symbols-outlined" aria-hidden="true">
              chevron_right
            </span>
            <span>Execution Phase</span>
          </div>
          <h1>Delay Mapping Sheet</h1>
          <p>{intro}</p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!rows.length}
          onClick={() => downloadDelayMappingSheet(rows)}
        >
          <span className="material-symbols-outlined" aria-hidden="true">
            download
          </span>
          Download Sheet
        </button>
      </div>

      <div className="delay-metrics">
        <article className="delay-metric delay-metric-rose">
          <div className="delay-metric-label">
            <span className="material-symbols-outlined" aria-hidden="true">
              schedule
            </span>
            <h3>Total Delayed Days</h3>
          </div>
          <p className="delay-metric-value tone-bad">
            {delayedDays}
            <span>Days</span>
          </p>
        </article>
        <article className="delay-metric delay-metric-amber">
          <div className="delay-metric-label">
            <span className="material-symbols-outlined" aria-hidden="true">
              warning
            </span>
            <h3>Delayed Tasks</h3>
          </div>
          <p className="delay-metric-value">
            {delayedTasks}
            <span className="muted-unit">Active</span>
          </p>
        </article>
      </div>

      <div className="delay-table-card">
        <div className="delay-table-head">
          <div className="delay-table-title">
            <span className="wsr-num" aria-hidden="true">
              <span className="material-symbols-outlined">table_rows</span>
            </span>
            <h2>Detailed Mapping</h2>
          </div>
        </div>
        {rows.length ? (
          <div className="delay-table-wrap">
            <table className="delay-table">
              <thead>
                <tr>
                  <th>Phase/Task Name</th>
                  <th>Planned Dates</th>
                  <th>Revised Dates</th>
                  <th>Delay</th>
                  <th>Primary Reason</th>
                  <th>Impact on Go-Live</th>
                  <th>Mitigation Plan</th>
                  <th>Owner</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={`${row.kind}-${row.wbs || row.name}-${index}`}>
                    <td>
                      <p className="delay-name">{row.name}</p>
                      <p className="delay-parent">
                        {row.parent_name || (row.kind === "phase" ? "Phase" : "Task")}
                      </p>
                    </td>
                    <td className="mono delay-dates">{dateWindow(row.planned_start, row.planned_finish)}</td>
                    <td className="mono delay-dates">{dateWindow(row.revised_start, row.revised_finish)}</td>
                    <td>
                      <DelayBadge days={row.delay_days} />
                    </td>
                    <td>{unavailable(row.primary_reason)}</td>
                    <td>
                      <GoLiveImpact value={row.go_live_impact} />
                    </td>
                    <td className="delay-mitigation" title={row.mitigation_plan || undefined}>
                      {unavailable(row.mitigation_plan)}
                    </td>
                    <td>
                      <OwnerCell name={row.owner} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="delay-empty-rows">No delayed phases or tasks in the uploaded plan</p>
        )}
      </div>
    </section>
  );
}

function dateWindow(start: string | null | undefined, finish: string | null | undefined): string {
  if (!start && !finish) {
    return "Unavailable";
  }
  if (start && finish) {
    return `${compactDate(start)} - ${compactDate(finish)}`;
  }
  return windowRange(start, finish);
}

function DelayBadge({ days }: { days: number | null | undefined }) {
  if (days == null || days <= 0) {
    return <span className="muted">Unavailable</span>;
  }
  const tone = days >= 7 ? "delay-chip-rose" : "delay-chip-amber";
  return <span className={`delay-chip ${tone}`}>+{days} Days</span>;
}

function GoLiveImpact({ value }: { value: DelayMappingRow["go_live_impact"] }) {
  if (value === "high") {
    return (
      <div className="delay-impact tone-bad">
        <span className="material-symbols-outlined" aria-hidden="true">
          arrow_upward
        </span>
        <strong>High</strong>
      </div>
    );
  }
  if (value === "medium") {
    return (
      <div className="delay-impact tone-warn">
        <span className="material-symbols-outlined" aria-hidden="true">
          remove
        </span>
        <strong>Medium</strong>
      </div>
    );
  }
  return <span className="muted">Unavailable</span>;
}

function OwnerCell({ name }: { name: string | null | undefined }) {
  const label = name?.trim();
  if (!label) {
    return <span className="muted">Unavailable</span>;
  }
  return (
    <div className="delay-owner">
      <span className="delay-avatar">{initials(label)}</span>
      <span>{label}</span>
    </div>
  );
}

function initials(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean);
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

function csvCell(value: string): string {
  if (/[",\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

function downloadDelayMappingSheet(rows: DelayMappingRow[]) {
  const header = [
    "Kind",
    "Phase/Task Name",
    "Parent",
    "WBS",
    "Planned Start",
    "Planned End",
    "Revised Start",
    "Revised End",
    "Delay Days",
    "Primary Reason",
    "Impact on Go-Live",
    "Mitigation Plan",
    "Owner",
  ];
  const body = rows.map((row) => [
    row.kind,
    row.name,
    row.parent_name || "",
    row.wbs || "",
    row.planned_start?.slice(0, 10) || "",
    row.planned_finish?.slice(0, 10) || "",
    row.revised_start?.slice(0, 10) || "",
    row.revised_finish?.slice(0, 10) || "",
    row.delay_days == null ? "" : String(row.delay_days),
    row.primary_reason || "",
    row.go_live_impact || "",
    row.mitigation_plan || "",
    row.owner || "",
  ]);
  const csv = [header, ...body].map((line) => line.map(csvCell).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "delay-mapping-sheet.csv";
  link.click();
  URL.revokeObjectURL(url);
}
