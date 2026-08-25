import { useState } from "react";
import { reviewLabel } from "../wsrFormat";
import type { AiDerivedItem } from "../types";

type Props = {
  item: AiDerivedItem;
  disabled?: boolean;
  onReview: (item: AiDerivedItem, decision: "kept" | "edited" | "removed", content?: string) => void;
  onViewSource: (item: AiDerivedItem) => void;
};

export function WsrInsightItem({ item, disabled, onReview, onViewSource }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.content);
  const source = item.evidence_references[0];

  return (
    <li className={`insight insight-${item.review_status}`}>
      <p>
        <span className="ai-tag">AI-derived</span> {item.content}
      </p>
      <p className="muted">
        Source / Evidence: {source?.task_or_milestone_name ?? "Unavailable"}
        {source?.date ? ` (${source.date})` : ""}
      </p>
      <p className="muted">Review: {reviewLabel(item.review_status)}</p>
      {editing ? (
        <div className="insight-edit">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            disabled={disabled}
            rows={3}
          />
          <button
            type="button"
            disabled={disabled || !draft.trim()}
            onClick={() => {
              onReview(item, "edited", draft.trim());
              setEditing(false);
            }}
          >
            Save edit
          </button>
          <button type="button" disabled={disabled} onClick={() => setEditing(false)}>
            Cancel
          </button>
        </div>
      ) : (
        <div className="actions">
          <button type="button" disabled={disabled} onClick={() => onReview(item, "kept")}>
            Keep
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => {
              setDraft(item.content);
              setEditing(true);
            }}
          >
            Edit
          </button>
          <button type="button" disabled={disabled} onClick={() => onReview(item, "removed")}>
            Remove
          </button>
          <button type="button" disabled={disabled} onClick={() => onViewSource(item)}>
            View Source
          </button>
        </div>
      )}
    </li>
  );
}
