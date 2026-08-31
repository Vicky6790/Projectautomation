import type { NamedDateValue } from "./types";

export function healthLabel(value: string | null | undefined): string {
  if (value === "on_track") {
    return "On track";
  }
  if (value === "at_risk") {
    return "At risk";
  }
  if (value === "off_track") {
    return "Off track";
  }
  if (value === "unavailable") {
    return "Unavailable — insufficient plan data";
  }
  return value || "Unavailable";
}

export function unavailable(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "Unavailable";
  }
  return String(value);
}

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "Unavailable";
  }
  return Number.isInteger(value) ? `${value}%` : `${value}%`;
}

export function namedDate(value: NamedDateValue | null | undefined): string {
  if (!value?.name) {
    return "Unavailable";
  }
  return value.date ? `${value.name} (${value.date})` : value.name;
}

export function phaseWbs(phase: { wbs?: string | null }, index: number): string {
  const value = phase.wbs?.trim();
  return value || `1.${index + 1}`;
}

export function phaseState(value: string | null | undefined): string {
  if (value === "not_started") {
    return "Not started";
  }
  if (value === "in_progress") {
    return "In progress";
  }
  if (value === "complete") {
    return "Complete";
  }
  return unavailable(value);
}

export function shortDate(value: string | null | undefined): string {
  if (!value) {
    return "Unavailable";
  }
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function weekDate(value: string | null | undefined): string {
  if (!value) {
    return "Unavailable";
  }
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  const day = String(parsed.getDate()).padStart(2, "0");
  const month = parsed.toLocaleDateString("en-GB", { month: "short" }).replace(".", "");
  return `${day}${month}${parsed.getFullYear()}`;
}

export function compactDate(value: string | null | undefined): string {
  if (!value) {
    return "Unavailable";
  }
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function parseDay(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function windowRange(
  start: string | null | undefined,
  finish: string | null | undefined,
  style: "arrow" | "dash" = "dash",
): string {
  const startDay = parseDay(start);
  const finishDay = parseDay(finish);
  if (!startDay && !finishDay) {
    return "Unavailable";
  }
  if (!startDay) {
    return style === "dash" ? shortDate(finish) : compactDate(finish);
  }
  if (!finishDay) {
    return style === "dash" ? shortDate(start) : compactDate(start);
  }
  const sameYear = startDay.getFullYear() === finishDay.getFullYear();
  const left = startDay.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  const right = finishDay.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    ...(sameYear && style === "arrow" ? {} : { year: "numeric" }),
  });
  const sep = style === "arrow" ? " → " : " – ";
  return `${left}${sep}${right}`;
}

export function durationDays(
  start: string | null | undefined,
  finish: string | null | undefined,
): number | null {
  const startDay = parseDay(start);
  const finishDay = parseDay(finish);
  if (!startDay || !finishDay) {
    return null;
  }
  const days = Math.round((finishDay.getTime() - startDay.getTime()) / 86_400_000) + 1;
  return days > 0 ? days : 1;
}

function mondayOf(isoDate: string): Date | null {
  const parsed = parseDay(isoDate);
  if (!parsed) {
    return null;
  }
  const weekday = (parsed.getDay() + 6) % 7;
  parsed.setDate(parsed.getDate() - weekday);
  return parsed;
}

function isoDay(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function publishWeekRange(
  asOf: string | null | undefined,
  weeksAhead = 0,
): string {
  if (!asOf) {
    return "Unavailable";
  }
  const start = mondayOf(asOf);
  if (!start) {
    return "Unavailable";
  }
  start.setDate(start.getDate() + weeksAhead * 7);
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  return `${shortDate(isoDay(start))} – ${shortDate(isoDay(end))}`;
}

export function personDaysLabel(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "Unavailable";
  }
  return `~${Math.round(value).toLocaleString("en-US")}`;
}

export function splitInsight(content: string): { title: string; body: string } {
  const separators = [" — ", " – ", ": "];
  for (const separator of separators) {
    const index = content.indexOf(separator);
    if (index > 8 && index < 80) {
      return { title: content.slice(0, index).trim(), body: content.slice(index + separator.length).trim() };
    }
  }
  const sentence = content.match(/^(.{12,72}?[.!?])\s+/);
  if (sentence) {
    return { title: sentence[1].replace(/[.!?]$/, ""), body: content.slice(sentence[0].length).trim() };
  }
  return { title: content, body: "" };
}
