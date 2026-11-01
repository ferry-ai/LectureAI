/** Subtitle cues. Playback emits a cue once, only while the playhead is on it. */

export interface Cue {
  start: number;
  end: number;
  text: string;
}

const STAMP = /(?:(\d+):)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})/;
const TAG = /<[^>]+>/g;

export function parseCues(raw: string): Cue[] {
  const text = raw.replace(/^\uFEFF/, "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const blocks = text.split(/\n{2,}/);
  const cues: Cue[] = [];
  for (const block of blocks) {
    const lines = block
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line && line !== "WEBVTT" && !line.startsWith("NOTE") && !line.startsWith("STYLE") && !line.startsWith("REGION"));
    const arrow = lines.findIndex((line) => line.includes("-->"));
    if (arrow < 0) continue;
    const timing = lines[arrow].split("-->");
    if (timing.length < 2) continue;
    const start = parseStamp(timing[0] ?? "");
    const end = parseStamp(timing[1] ?? "");
    if (start === null || end === null || end < start) continue;
    const spoken = lines
      .slice(arrow + 1)
      .join(" ")
      .replace(TAG, "")
      .replace(/&nbsp;/g, " ")
      .replace(/&amp;/g, "&")
      .replace(/\s+/g, " ")
      .trim();
    if (!spoken) continue;
    cues.push({ start, end, text: spoken });
  }
  cues.sort((left, right) => left.start - right.start);
  return cues;
}

export function cueKey(cue: Cue): string {
  return `${cue.start.toFixed(3)}|${cue.text}`;
}

/** Cues whose start the playhead has just crossed. A seek skips the gap instead of replaying it. */
export function cuesAtPlayhead(cues: Cue[], time: number, sent: Set<string>, windowSec = 0.8): Cue[] {
  const fresh: Cue[] = [];
  for (const cue of cues) {
    if (cue.start > time + 0.05) break;
    if (time - cue.start > windowSec) continue;
    const key = cueKey(cue);
    if (sent.has(key)) continue;
    sent.add(key);
    fresh.push(cue);
  }
  return fresh;
}

function parseStamp(value: string): number | null {
  const match = STAMP.exec(value.trim());
  if (!match) return null;
  const hours = match[1] ? Number(match[1]) : 0;
  const minutes = Number(match[2]);
  const seconds = Number(match[3]);
  const millis = Number((match[4] ?? "0").padEnd(3, "0").slice(0, 3));
  if ([hours, minutes, seconds, millis].some((part) => Number.isNaN(part))) return null;
  return hours * 3600 + minutes * 60 + seconds + millis / 1000;
}
