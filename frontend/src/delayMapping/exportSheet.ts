import { delaySheetDate } from "../wsrFormat";
import type { CompareMppResult, DelayMappingItem } from "./types";

export function exportDelayMappingExcel(result: CompareMppResult, rows: DelayMappingItem[]): void {
  const asOf = result.summary.asOf ? delaySheetDate(result.summary.asOf) : "Unavailable";
  const groups: { phase: string; rows: DelayMappingItem[] }[] = [];
  for (const row of rows) {
    const phase = row.parentName || "Other";
    const last = groups[groups.length - 1];
    if (last && last.phase === phase) {
      last.rows.push(row);
    } else {
      groups.push({ phase, rows: [row] });
    }
  }
  const total = rows.reduce((sum, row) => sum + (row.delayDays ?? 0), 0);
  const body = groups
    .flatMap((group) => [
      `<tr><td colspan="4"><b>${esc(group.phase)}</b></td></tr>`,
      ...group.rows.map(
        (row) => `<tr>
        <td>${esc(row.taskName)}</td>
        <td>${esc(row.taskType)}</td>
        <td style="text-align:left">${row.delayDays == null ? "Unavailable" : String(row.delayDays)}</td>
        <td>${esc(row.owner || "Unavailable")}</td>
      </tr>`,
      ),
    ])
    .join("");
  const html = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel">
<head><meta charset="UTF-8" /></head>
<body>
<table border="1">
  <tr><th colspan="2">Delay Mapping Sheet</th></tr>
  <tr><td>Baselined Go-Live Date</td><td>${esc(delaySheetDate(result.summary.baselineGoLive))}</td></tr>
  <tr><td>Current Go-Live Date (As On ${esc(asOf)})</td><td>${esc(delaySheetDate(result.summary.currentGoLive))}</td></tr>
  <tr><td>Shift In Working Days (As On ${esc(asOf)})</td><td>${esc(shiftLabel(result.summary.shiftWorkingDays))}</td></tr>
  <tr><td>Holidays In Above Duration</td><td>${esc(countLabel(result.summary.holidays))}</td></tr>
  <tr><td>Actual Shift In Working Days (As On ${esc(asOf)})</td><td>${esc(shiftLabel(result.summary.actualShiftWorkingDays))}</td></tr>
  <tr></tr>
  <tr>
    <th>Task Name</th>
    <th>Task Type?</th>
    <th>Shift Days Count</th>
    <th>Owner</th>
  </tr>
  ${body}
  <tr><td colspan="2"><b>Total Count</b></td><td style="text-align:left"><b>${total}</b></td><td></td></tr>
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
  return value == null ? "Unavailable" : `${value} days shift`;
}

function countLabel(value: number | null): string {
  return value == null ? "Unavailable" : String(value);
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
