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

export function reviewLabel(value: string | null | undefined): string {
  if (value === "kept") {
    return "Kept";
  }
  if (value === "edited") {
    return "Edited";
  }
  if (value === "removed") {
    return "Removed";
  }
  return "Pending";
}
