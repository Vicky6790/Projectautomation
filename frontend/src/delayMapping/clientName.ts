/** Client name from an uploaded MPP: drop date, "Project Plan (Naming)", and version. */
export function clientNameFromFilename(filename: string | null | undefined): string {
  let name = String(filename || "")
    .replace(/^.*[\\/]/, "")
    .replace(/\.[^./\\]+$/, "")
    .trim();
  if (!name) {
    return "";
  }
  name = name.replace(/\([^)]*\)/g, " ");
  name = name.replace(/\b(?:19|20)\d{2}[-./]\d{1,2}[-./]\d{1,2}\b/g, " ");
  name = name.replace(/\b\d{1,2}[-./]\d{1,2}[-./](?:\d{2}|\d{4})\b/g, " ");
  name = name.replace(/[_-]+/g, " ");
  name = name.replace(/\bproject\s*plan\b/gi, " ");
  name = name.replace(/\bprojectplan\b/gi, " ");
  name = name.replace(/\b[vV]\.?\d+\b/g, " ");
  name = name.replace(/\b(?:19|20)\d{2}\s+\d{1,2}\s+\d{1,2}\b/g, " ");
  name = name.replace(/\b\d{1,2}\s+\d{1,2}\s+(?:\d{2}|\d{4})\b/g, " ");
  name = name.replace(/\b\d{8}\b/g, " ");
  name = name.replace(/\b\d{6}\b/g, " ");
  name = name.replace(/\s+/g, " ").trim();
  if (!name || /^(?:plan|project|mpp)$/i.test(name)) {
    return "";
  }
  return name;
}

export function delayMappingPrintTitle(filename: string | null | undefined): string {
  const client = clientNameFromFilename(filename);
  return client ? `Delay Mapping Sheet — ${client}` : "Delay Mapping Sheet";
}
