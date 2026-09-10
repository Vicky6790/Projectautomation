import html2canvas from "html2canvas";
import { jsPDF } from "jspdf";

const A4_LANDSCAPE_WIDTH_MM = 297;

export async function downloadLandscapePdf(selector: string, filename: string): Promise<void> {
  const source = document.querySelector(selector);
  if (!(source instanceof HTMLElement)) {
    throw new Error("Report is not ready to save.");
  }

  const captureWidth = Math.max(source.scrollWidth, 1280);
  const canvas = await html2canvas(source, {
    scale: 2,
    backgroundColor: "#ffffff",
    useCORS: true,
    logging: false,
    width: captureWidth,
    height: source.scrollHeight,
    windowWidth: captureWidth,
    windowHeight: source.scrollHeight,
    onclone(clonedDoc) {
      const cloned = clonedDoc.querySelector(selector);
      if (!(cloned instanceof HTMLElement)) {
        return;
      }
      cloned.querySelectorAll(".wsr-project-pane").forEach((node) => {
        if (node instanceof HTMLElement) {
          node.style.display = "block";
          node.style.pageBreakAfter = "always";
          node.style.breakAfter = "page";
        }
      });
      cloned.querySelectorAll(".dms-no-print, .wsr-project-tabs, .pa-print-view-bar").forEach((node) => {
        if (node instanceof HTMLElement) {
          node.style.display = "none";
        }
      });
      const title = cloned.querySelector(".dms-print-title");
      if (title instanceof HTMLElement) {
        title.style.display = "block";
        title.style.margin = "0 0 16px";
      }
      cloned.style.width = `${captureWidth}px`;
      cloned.style.maxWidth = "none";
      cloned.style.overflow = "visible";
      cloned.style.height = "auto";
      const kpi = cloned.querySelector(".kpi-grid");
      if (kpi instanceof HTMLElement) {
        kpi.style.gridTemplateColumns = "repeat(4, minmax(0, 1fr))";
      }
      const hero = cloned.querySelector(".wsr-hero");
      if (hero instanceof HTMLElement) {
        hero.style.flexWrap = "nowrap";
      }
      cloned.querySelectorAll(".gantt-exec, .gantt-exec-inner, .gantt-track-exec, .gantt-row-exec").forEach((node) => {
        if (node instanceof HTMLElement) {
          node.style.overflow = "visible";
          node.style.minWidth = "0";
        }
      });
    },
  });

  const widthMm = A4_LANDSCAPE_WIDTH_MM;
  const heightMm = Math.max((canvas.height * widthMm) / canvas.width, 210);
  const pdf = new jsPDF({
    unit: "mm",
    format: [widthMm, heightMm],
  });
  pdf.addImage(canvas.toDataURL("image/png"), "PNG", 0, 0, widthMm, heightMm, undefined, "FAST");
  pdf.save(filename.endsWith(".pdf") ? filename : `${filename}.pdf`);
}
