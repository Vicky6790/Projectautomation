import { useEffect, useMemo, useState } from "react";
import {
  ApiRequestError,
  approvePlan,
  downloadPlanMpp,
  getPlanLibrary,
  previewPlan,
  retryJob,
  retryPlanPreview,
} from "./api";
import type {
  GeneratedPlan,
  LibraryPhase,
  PhaseSelection,
  PlanLibrary,
  PlanResult,
  ProcessingResponse,
} from "./types";

const BRAND_MODES = new Set(["brand_guidelines_existing", "brand_guidelines_create"]);

function asPlanResult(result: ProcessingResponse["result"]): PlanResult | null {
  if (!result || typeof result !== "object") {
    return null;
  }
  const data = result as PlanResult;
  return {
    plan: data.plan,
    approved: Boolean(data.approved),
    mpp_available: Boolean(data.mpp_available),
  };
}

function emptySelection(phaseId: string): PhaseSelection {
  return { phase_id: phaseId, deliverables: [], set_overrides: {} };
}

export function PlanGeneratorView() {
  const [library, setLibrary] = useState<PlanLibrary | null>(null);
  const [name, setName] = useState("Generated Plan");
  const [commonSetCount, setCommonSetCount] = useState(1);
  const [phases, setPhases] = useState<PhaseSelection[]>([]);
  const [addPhaseId, setAddPhaseId] = useState("");
  const [job, setJob] = useState<ProcessingResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Loading the template library…");

  const result = asPlanResult(job?.result ?? null);
  const plan = result?.plan ?? null;
  const approved = result?.approved ?? false;
  const mppAvailable = result?.mpp_available ?? false;

  const phaseById = useMemo(() => {
    const map = new Map<string, LibraryPhase>();
    for (const phase of library?.phases ?? []) {
      map.set(phase.id, phase);
    }
    return map;
  }, [library]);

  const unusedPhases = useMemo(
    () => (library?.phases ?? []).filter((phase) => !phases.some((item) => item.phase_id === phase.id)),
    [library, phases],
  );

  useEffect(() => {
    void getPlanLibrary()
      .then((data) => {
        setLibrary(data);
        setMessage("Add at least one phase, then preview the work breakdown structure.");
      })
      .catch((error: unknown) => {
        setMessage(error instanceof Error ? error.message : "Failed to load the template library");
      });
  }, []);

  function updatePhase(index: number, next: PhaseSelection) {
    setPhases((current) => current.map((item, itemIndex) => (itemIndex === index ? next : item)));
  }

  function addPhase() {
    const phaseId = addPhaseId || unusedPhases[0]?.id;
    if (!phaseId) {
      return;
    }
    setPhases((current) => [...current, emptySelection(phaseId)]);
    setAddPhaseId("");
    setJob(null);
  }

  function removePhase(index: number) {
    setPhases((current) => current.filter((_, itemIndex) => itemIndex !== index));
    setJob(null);
  }

  function movePhase(index: number, offset: number) {
    const target = index + offset;
    if (target < 0 || target >= phases.length) {
      return;
    }
    setPhases((current) => {
      const next = [...current];
      const [item] = next.splice(index, 1);
      next.splice(target, 0, item);
      return next;
    });
    setJob(null);
  }

  function toggleDeliverable(index: number, deliverableId: string) {
    const selection = phases[index];
    const selected = new Set(selection.deliverables);
    if (BRAND_MODES.has(deliverableId)) {
      const alreadyOn = selected.has(deliverableId);
      for (const mode of BRAND_MODES) {
        selected.delete(mode);
      }
      if (!alreadyOn) {
        selected.add(deliverableId);
      }
    } else if (selected.has(deliverableId)) {
      selected.delete(deliverableId);
    } else {
      selected.add(deliverableId);
    }
    const overrides = { ...selection.set_overrides };
    if (!selected.has(deliverableId)) {
      delete overrides[deliverableId];
    }
    updatePhase(index, { ...selection, deliverables: [...selected], set_overrides: overrides });
    setJob(null);
  }

  function describeConflict(error: ApiRequestError): string {
    const pairs = error.details?.conflicting_phases;
    if (!Array.isArray(pairs)) {
      return error.message;
    }
    const names = (pairs as string[][])
      .map((pair) => pair.map((id) => phaseById.get(id)?.name ?? id).join(" before "))
      .join("; ");
    return names ? `${error.message}: ${names}` : error.message;
  }

  async function runPreview() {
    if (!phases.length) {
      setMessage("At least one phase is required.");
      return;
    }
    setBusy(true);
    setMessage("Generating preview…");
    try {
      const next = await previewPlan({
        name,
        common_set_count: commonSetCount,
        phases,
      });
      setJob(next);
      setMessage(next.status === "succeeded" ? "Preview ready. Review the WBS, then approve." : "Preview failed.");
    } catch (error: unknown) {
      setMessage(error instanceof ApiRequestError ? describeConflict(error) : "Preview failed");
    } finally {
      setBusy(false);
    }
  }

  async function retry() {
    if (!job) {
      return;
    }
    setBusy(true);
    try {
      const next =
        job.status === "failed" && result?.plan
          ? await retryJob("plan", job.id)
          : await retryPlanPreview(job.id);
      setJob(next);
      setMessage(next.status === "succeeded" ? "Retry complete." : "Retry finished with errors.");
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Retry failed");
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!job) {
      return;
    }
    setBusy(true);
    setMessage("Generating the Microsoft Project file…");
    try {
      const next = await approvePlan(job.id);
      setJob(next);
      setMessage(next.status === "succeeded" ? "Plan file is ready to download." : "MPP generation failed.");
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Approval failed");
    } finally {
      setBusy(false);
    }
  }

  async function download() {
    if (!job) {
      return;
    }
    try {
      const blob = await downloadPlanMpp(job.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "generated-plan.xml";
      link.click();
      URL.revokeObjectURL(url);
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Download failed");
    }
  }

  return (
    <section className="panel">
      <h2>Plan Generator</h2>
      <p>{message}</p>
      <label>
        Plan name
        <input value={name} onChange={(event) => setName(event.target.value)} disabled={busy} />
      </label>
      <label>
        Common set count
        <input
          type="number"
          min={1}
          max={99}
          value={commonSetCount}
          onChange={(event) => {
            setCommonSetCount(Number(event.target.value));
            setJob(null);
          }}
          disabled={busy}
        />
      </label>
      <div className="actions">
        <select
          value={addPhaseId}
          onChange={(event) => setAddPhaseId(event.target.value)}
          disabled={busy || unusedPhases.length === 0}
        >
          <option value="">Add a phase</option>
          {unusedPhases.map((phase) => (
            <option key={phase.id} value={phase.id}>
              {phase.name}
            </option>
          ))}
        </select>
        <button type="button" onClick={addPhase} disabled={busy || unusedPhases.length === 0}>
          Add phase
        </button>
      </div>
      {phases.length === 0 ? <p className="muted">Phase configuration is empty.</p> : null}
      {phases.map((selection, index) => {
        const phase = phaseById.get(selection.phase_id);
        if (!phase) {
          return null;
        }
        return (
          <article className="phase-card" key={`${selection.phase_id}-${index}`}>
            <header>
              <h3>
                {index + 1}. {phase.name}
              </h3>
              <div className="actions">
                <button type="button" onClick={() => movePhase(index, -1)} disabled={busy || index === 0}>
                  Move up
                </button>
                <button type="button" onClick={() => movePhase(index, 1)} disabled={busy || index === phases.length - 1}>
                  Move down
                </button>
                <button type="button" onClick={() => removePhase(index)} disabled={busy}>
                  Remove
                </button>
              </div>
            </header>
            <ul className="deliverables">
              {phase.deliverables.map((item) => {
                const checked = selection.deliverables.includes(item.id);
                return (
                  <li key={item.id}>
                    <label>
                      <input
                        type={BRAND_MODES.has(item.id) ? "radio" : "checkbox"}
                        name={BRAND_MODES.has(item.id) ? `brand-${index}` : item.id}
                        checked={checked}
                        onChange={() => toggleDeliverable(index, item.id)}
                        disabled={busy}
                      />
                      {item.name}
                    </label>
                    {item.set_based && checked ? (
                      <label>
                        Sets
                        <input
                          type="number"
                          min={1}
                          max={99}
                          value={selection.set_overrides[item.id] ?? commonSetCount}
                          onChange={(event) => {
                            updatePhase(index, {
                              ...selection,
                              set_overrides: {
                                ...selection.set_overrides,
                                [item.id]: Number(event.target.value),
                              },
                            });
                            setJob(null);
                          }}
                          disabled={busy}
                        />
                      </label>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </article>
        );
      })}
      <div className="actions">
        <button type="button" onClick={() => void runPreview()} disabled={busy}>
          Preview plan
        </button>
        {job?.status === "failed" ? (
          <button type="button" onClick={() => void retry()} disabled={busy}>
            Retry
          </button>
        ) : null}
        {job?.status === "succeeded" && plan && !approved ? (
          <button type="button" onClick={() => void approve()} disabled={busy}>
            Approve and generate MPP
          </button>
        ) : null}
        {approved && mppAvailable ? (
          <button type="button" onClick={() => void download()} disabled={busy}>
            Download MPP
          </button>
        ) : null}
      </div>
      {busy ? <p className="processing">Processing…</p> : null}
      {plan ? <WbsPreview plan={plan} /> : null}
    </section>
  );
}

function WbsPreview({ plan }: { plan: GeneratedPlan }) {
  return (
    <div className="wbs">
      <h3>{plan.name}</h3>
      <ol>
        {plan.tasks.map((task) => (
          <li key={task.id} style={{ marginLeft: (task.outline_level - 1) * 16 }}>
            <strong>{task.name}</strong>
            {task.is_milestone ? " · milestone" : null}
            {task.set_name ? ` · ${task.set_name}` : null}
            {task.predecessor_ids.length ? ` · predecessors ${task.predecessor_ids.join(", ")}` : null}
          </li>
        ))}
      </ol>
    </div>
  );
}
