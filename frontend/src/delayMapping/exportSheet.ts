import { shortDate } from "../wsrFormat";
import type { CompareMppResult, DelayMappingItem } from "./types";

export function exportDelayMappingExcel(result: CompareMppResult, rows: DelayMappingItem[]): void {
  const html = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel">
<head><meta charset="UTF-8" /></head>
<body>
<table border="1">
  <tr><th colspan="7">DELAY MAPPING</th></tr>
  <tr><td colspan="7">Tasks whose Baseline Finish is NA</td></tr>
  <tr></tr>
  <tr><td>Total tasks read</td><td>${result.summary.tasksRead}</td></tr>
  <tr><td>Tasks with Baseline Finish = NA</td><td>${result.summary.baselineFinishNaCount}</td></tr>
  <tr><td>Delay Sheet rows generated</td><td>${result.summary.delaySheetRows}</td></tr>
  <tr></tr>
  <tr>
    <th>Task ID</th>
    <th>Task Name</th>
    <th>WBS</th>
    <th>Start</th>
    <th>Baseline Finish</th>
    <th>Finish</th>
    <th>Predecessors</th>
  </tr>
  ${rows
    .map((row) => {
      return `<tr>
        <td>${esc(row.taskId)}</td>
        <td>${esc(row.taskName)}</td>
        <td>${esc(row.wbs || "")}</td>
        <td>${esc(shortDate(row.currentStart))}</td>
        <td>${esc(row.baselineFinish || "")}</td>
        <td>${esc(shortDate(row.currentFinish))}</td>
        <td>${esc(row.predecessors.join(", "))}</td>
      </tr>`;
    })
    .join("")}
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
