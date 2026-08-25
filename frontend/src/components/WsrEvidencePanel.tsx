import { reviewLabel, unavailable } from "../wsrFormat";
import type { WsrEvidenceResponse } from "../types";

type Props = {
  evidence: WsrEvidenceResponse;
  onClose: () => void;
};

export function WsrEvidencePanel({ evidence, onClose }: Props) {
  return (
    <aside className="evidence-panel" role="dialog" aria-label="Source detail">
      <header>
        <h3>Source / Evidence</h3>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </header>
      <p>{evidence.content}</p>
      <p className="muted">Review status: {reviewLabel(evidence.review_status)}</p>
      {evidence.evidence_references.map((reference, index) => (
        <dl key={`${reference.task_or_milestone_name}-${index}`} className="evidence-facts">
          <dt>Task or milestone</dt>
          <dd>{unavailable(reference.task_or_milestone_name)}</dd>
          <dt>Date</dt>
          <dd>{unavailable(reference.date)}</dd>
          <dt>Progress</dt>
          <dd>
            {reference.progress === null || reference.progress === undefined
              ? "Unavailable"
              : `${reference.progress}%`}
          </dd>
          <dt>Predecessors</dt>
          <dd>
            {reference.predecessor_names?.length
              ? reference.predecessor_names.join(", ")
              : "Unavailable"}
          </dd>
          <dt>Resource assignments</dt>
          <dd>
            {reference.resource_assignments?.length
              ? reference.resource_assignments.join(", ")
              : "Unavailable"}
          </dd>
          <dt>Dependency</dt>
          <dd>{unavailable(reference.dependency_description)}</dd>
        </dl>
      ))}
    </aside>
  );
}
