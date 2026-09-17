import html2canvas from "html2canvas";
import { jsPDF } from "jspdf";

const A4_LANDSCAPE_WIDTH_MM = 297;
const MAX_CANVAS_EDGE = 8192;

function unlockOverflow(root: ParentNode, target?: HTMLElement | null) {
  const nodes: HTMLElement[] = [];
  const doc = root instanceof Document ? root : target?.ownerDocument ?? document;
  nodes.push(doc.documentElement, doc.body);
  let node: HTMLElement | null = target ?? null;
  while (node) {
    nodes.push(node);
    node = node.parentElement;
  }
  root.querySelectorAll<HTMLElement>(
    ".shell, .shell-main, .shell-content, .wsr-page, .dms-page, .wsr-report, .dms-report, .dashboard, .wsr-project-pane, .wsr-section, .wsr-hero, .gantt-exec, .gantt-exec-inner, .gantt-track-exec, .dms-sheet, .dms-table-wrap",
  ).forEach((item) => nodes.push(item));
  const seen = new Set<HTMLElement>();
  for (const item of nodes) {
    if (seen.has(item)) {
      continue;
    }
    seen.add(item);
    item.style.setProperty("overflow", "visible", "important");
    item.style.setProperty("overflow-x", "visible", "important");
    item.style.setProperty("overflow-y", "visible", "important");
    item.style.setProperty("height", "auto", "important");
    item.style.setProperty("max-height", "none", "important");
    item.style.setProperty("max-width", "none", "important");
  }
}

function copyHeadAssets(from: Document, to: Document) {
  from.querySelectorAll('link[rel="stylesheet"], link[rel="preconnect"], style').forEach((node) => {
    to.head.appendChild(node.cloneNode(true));
  });
}

function waitStyles(doc: Document): Promise<void> {
  const links = Array.from(doc.querySelectorAll('link[rel="stylesheet"]')) as HTMLLinkElement[];
  return Promise.all(
    links.map(
      (link) =>
        new Promise<void>((resolve) => {
          if (link.sheet) {
            resolve();
            return;
          }
          link.addEventListener("load", () => resolve(), { once: true });
          link.addEventListener("error", () => resolve(), { once: true });
        }),
    ),
  ).then(async () => {
    if (doc.fonts?.ready) {
      await doc.fonts.ready.catch(() => undefined);
    }
  });
}

function nextPaint(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  });
}

function openCaptureFrame(): { iframe: HTMLIFrameElement; doc: Document } {
  const iframe = document.createElement("iframe");
  iframe.setAttribute("aria-hidden", "true");
  iframe.setAttribute("tabindex", "-1");
  iframe.title = "Print capture";
  document.body.appendChild(iframe);
  const doc = iframe.contentDocument;
  if (!doc) {
    iframe.remove();
    throw new Error("Print frame is not ready.");
  }
  doc.open();
  doc.write("<!DOCTYPE html><html><head></head><body></body></html>");
  doc.close();
  return { iframe, doc };
}

function prepareClone(clone: HTMLElement, widthPx: number) {
  clone.querySelectorAll<HTMLElement>(".wsr-project-pane").forEach((pane) => {
    pane.style.setProperty("display", "block", "important");
  });
  clone.querySelectorAll<HTMLElement>(".gantt-head-exec").forEach((node) => {
    node.style.position = "static";
  });
  clone.style.margin = "0";
  clone.style.width = `${widthPx}px`;
  clone.style.maxWidth = "none";
  clone.style.minWidth = `${widthPx}px`;
  clone.style.height = "auto";
  clone.style.overflow = "visible";
}

function measureContent(el: HTMLElement, minWidth: number, minHeight: number) {
  const box = el.getBoundingClientRect();
  const width = Math.ceil(
    Math.max(minWidth, box.width, el.scrollWidth, el.offsetWidth, ...Array.from(el.children).map((child) => (child as HTMLElement).scrollWidth || 0)),
  );
  const height = Math.ceil(Math.max(minHeight, box.height, el.scrollHeight, el.offsetHeight));
  return { width, height };
}

export async function downloadLandscapePdf(selector: string, filename: string): Promise<void> {
  const source = document.querySelector(selector);
  if (!(source instanceof HTMLElement)) {
    throw new Error("Report is not ready to save.");
  }

  const previewBox = source.getBoundingClientRect();
  const previewWidth = Math.ceil(Math.max(previewBox.width, source.clientWidth, 800));
  const { iframe, doc } = openCaptureFrame();

  try {
    copyHeadAssets(document, doc);
    doc.documentElement.className = "pa-print-view pa-print-capture";
    doc.documentElement.style.cssText =
      "overflow:visible !important;max-width:none !important;width:auto;height:auto;background:#ffffff";
    doc.body.style.cssText =
      "margin:0;overflow:visible !important;max-width:none !important;background:#ffffff;width:auto;height:auto";

    const clone = source.cloneNode(true) as HTMLElement;
    prepareClone(clone, previewWidth);
    doc.body.appendChild(clone);

    iframe.style.cssText = [
      "position:fixed",
      "left:0",
      "top:0",
      `width:${previewWidth}px`,
      "height:8000px",
      "border:0",
      "margin:0",
      "padding:0",
      "opacity:0",
      "pointer-events:none",
      "background:#ffffff",
    ].join(";");

    await waitStyles(doc);
    await nextPaint();
    unlockOverflow(doc, clone);

    let { width, height } = measureContent(clone, previewWidth, 1);
    iframe.style.width = `${width}px`;
    iframe.style.height = `${height}px`;
    clone.style.width = `${width}px`;
    clone.style.minWidth = `${width}px`;
    await nextPaint();
    ({ width, height } = measureContent(clone, width, height));
    height += 16;
    iframe.style.width = `${width}px`;
    iframe.style.height = `${height}px`;

    const scale = Math.max(
      1,
      Math.min(2, MAX_CANVAS_EDGE / Math.max(width, 1), MAX_CANVAS_EDGE / Math.max(height, 1)),
    );
    const canvas = await html2canvas(clone, {
      scale,
      backgroundColor: "#ffffff",
      useCORS: true,
      logging: false,
      imageTimeout: 0,
      width,
      height,
      windowWidth: width,
      windowHeight: height,
      x: 0,
      y: 0,
      scrollX: 0,
      scrollY: 0,
      onclone(clonedDoc, clonedEl) {
        clonedDoc.documentElement.classList.add("pa-print-view", "pa-print-capture");
        clonedDoc.documentElement.style.cssText =
          "overflow:visible !important;max-width:none !important;width:auto;height:auto;background:#ffffff";
        clonedDoc.body.style.cssText =
          "margin:0;overflow:visible !important;max-width:none !important;background:#ffffff";
        unlockOverflow(clonedDoc, clonedEl);
        prepareClone(clonedEl, width);
        clonedEl.style.width = `${width}px`;
        clonedEl.style.minWidth = `${width}px`;
        clonedEl.style.height = "auto";
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
  } finally {
    iframe.remove();
  }
}

export function printWithWsrEngine(selector: string): Promise<void> {
  const source = document.querySelector(selector);
  if (!(source instanceof HTMLElement)) {
    return Promise.reject(new Error("Report is not ready to save."));
  }

  const heightPx = Math.ceil(Math.max(source.scrollHeight, source.getBoundingClientRect().height));
  const heightMm = Math.max(Math.ceil((heightPx / 96) * 25.4 * 1.2) + 20, 210);
  const pageStyle = document.createElement("style");
  pageStyle.id = "wsr-print-page";
  pageStyle.textContent = `@media print { @page { size: 297mm ${heightMm}mm; margin: 0; } }`;
  document.head.appendChild(pageStyle);
  document.documentElement.classList.add("wsr-printing");

  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) {
        return;
      }
      settled = true;
      window.removeEventListener("afterprint", finish);
      media.removeEventListener("change", onMedia);
      document.documentElement.classList.remove("wsr-printing");
      pageStyle.remove();
      resolve();
    };
    const media = window.matchMedia("print");
    const onMedia = (event: MediaQueryListEvent) => {
      if (!event.matches) {
        finish();
      }
    };
    window.addEventListener("afterprint", finish);
    media.addEventListener("change", onMedia);
    window.print();
  });
}
