import { shortDate, unavailable } from "../wsrFormat";
import type { CompareMppResult, DelayMappingItem } from "./types";

export function exportDelayMappingExcel(result: CompareMppResult, rows: DelayMappingItem[]): void {
  const html = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel">
<head><meta charset="UTF-8" /></head>
<body>
<table border="1">
  <tr><th colspan="9">DELAY MAPPING</th></tr>
  <tr><td colspan="9">Tasks that move the project deadline</td></tr>
  <tr></tr>
  <tr><td>Project Deadline</td><td>${esc(shortDate(result.summary.currentGoLive))}</td></tr>
  <tr><td>Identified Deadline Impact</td><td>${shiftLabel(result.summary.goLiveShift)}</td></tr>
  <tr><td>Delayed Tasks</td><td>${result.summary.delayedTaskCount}</td></tr>
  <tr><td>Additional Tasks</td><td>${result.summary.additionalTaskCount}</td></tr>
  <tr></tr>
  <tr>
    <th>Task Name</th>
    <th>Task Type</th>
    <th>Start</th>
    <th>Baseline Finish</th>
    <th>Finish</th>
    <th>Delay / Impact Days</th>
    <th>Predecessors</th>
    <th>Owner</th>
    <th>Impact Reason</th>
  </tr>
  ${rows
    .map((row) => {
      const fill = row.taskType === "DELAYED" ? "#FEF2F2" : "#FFF7ED";
      const baseline = row.taskType === "ADDITIONAL" ? "N/A" : shortDate(row.baselineFinish);
      const impact = row.goLiveImpact > 0 ? `+${row.goLiveImpact} WD` : row.taskType === "ADDITIONAL" ? "N/A" : "0";
      return `<tr>
        <td style="background:${fill}">${esc(row.taskName)}</td>
        <td style="background:${fill}">${esc(row.taskType)}</td>
        <td style="background:${fill}">${esc(shortDate(row.currentStart))}</td>
        <td style="background:${fill}">${esc(baseline)}</td>
        <td style="background:${fill}">${esc(shortDate(row.currentFinish))}</td>
        <td style="background:${fill}">${esc(impact)}</td>
        <td style="background:${fill}">${esc(row.predecessors.join(", ") || "Unavailable")}</td>
        <td style="background:${fill}">${esc(unavailable(row.owner))}</td>
        <td style="background:${fill}">${esc(row.evidence)}</td>
      </tr>`;
    })
    .join("")}
  <tr>
    <td><b>Total</b></td>
    <td></td>
    <td></td>
    <td></td>
    <td></td>
    <td><b>${rows.reduce((sum, row) => sum + (row.goLiveImpact || 0), 0)}</b></td>
    <td></td>
    <td></td>
    <td></td>
  </tr>
</table>
</body>
</html>`;
  downloadBlob(
    new Blob(["\ufeff", html], { type: "application/vnd.ms-excel" }),
    "delay-mapping.xls",
  );
}

export function printDelayMappingSheet(): void {
  const root = document.documentElement;
  root.classList.add("dms-printing");
  const restore = () => {
    root.classList.remove("dms-printing");
    window.removeEventListener("afterprint", restore);
  };
  window.addEventListener("afterprint", restore);
  window.print();
  window.setTimeout(restore, 1000);
}

function shiftLabel(value: number | null): string {
  if (value == null) {
    return "Unavailable";
  }
  return value > 0 ? `+${value} Working Days` : `${value} Working Days`;
}

function esc(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
