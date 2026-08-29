import { useContext, useEffect, useState } from "react";
import { Navigate, Link } from "react-router-dom";
import { getWsrRequest } from "./api";
import { DelayMappingPanel, downloadDelayMappingSheet } from "./components/DelayMappingPanel";
import { ShellMetaContext } from "./shellMeta";
import type { DelayMappingSheet, WsrPlanFacts } from "./types";
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

  const mapping: DelayMappingSheet = facts?.delay_mapping ?? {};
  const asOf = facts?.as_of_date;

  if (!handle) {
    return <Navigate to="/wsr" replace />;
  }

  if (!facts) {
    return (
      <section className="delay-page">
        <div className="delay-empty">
          <h2>Go-Live Delay Mapping</h2>
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
            <span>Go-Live Delay Mapping</span>
          </div>
          <h1>Go-Live Delay Mapping</h1>
          <p>
            Working-day Go-Live shift from the baseline versus current MPP. The register lists
            Delay and Additional tasks that have an owner. Unattributed leftover days are not
            shown as extra rows.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => downloadDelayMappingSheet(mapping, asOf)}
        >
          <span className="material-symbols-outlined" aria-hidden="true">
            download
          </span>
          Download Sheet
        </button>
      </div>
      <DelayMappingPanel mapping={mapping} asOf={asOf} />
    </section>
  );
}
