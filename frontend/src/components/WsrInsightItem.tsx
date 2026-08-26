import type { AiDerivedItem } from "../types";

type Props = {
  item: AiDerivedItem;
  tone?: "risk" | "need";
};

export function WsrInsightItem({ item, tone }: Props) {
  return (
    <li className={`insight${tone ? ` insight-${tone}` : ""}`}>
      <p>
        <span className="ai-tag">AI-derived</span> {item.content}
      </p>
    </li>
  );
}
