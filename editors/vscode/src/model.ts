// Pure logic for the grokmap extension: no `vscode` import, so it can be unit-tested with node.

export type State = "human" | "understood" | "fading" | "skimmed" | "unread" | "uncommitted";

export interface LineInfo {
  line: number; // 1-based, as git blame reports it
  state: State;
  sha?: string;
  agent?: string;
  understood_by?: string[];
}

export interface CommitInfo {
  author: string;
  date: string;
  summary: string;
  agent: string | null;
}

export interface Summary {
  lines: number;
  human: number;
  ai: number;
  understood: number;
  fading: number;
  skimmed: number;
  unread: number;
  debt_pct: number;
  tools: Record<string, number>;
  people: Record<string, number>;
}

export interface FileData {
  path: string;
  tracked: boolean;
  note?: string;
  critical?: boolean;
  summary?: Summary;
  commits?: Record<string, CommitInfo>;
  lines: LineInfo[];
}

export interface Span {
  state: State;
  start: number; // 1-based, inclusive
  end: number; // 1-based, inclusive
  sha?: string;
  agent?: string;
  understoodBy: string[];
}

/** States that get a colour in the gutter. Human-written and uncommitted lines are left alone. */
export const DECORATED: State[] = ["unread", "skimmed", "fading", "understood"];

export const LABELS: Record<State, string> = {
  unread: "Nobody has checked this",
  skimmed: "Only skimmed",
  fading: "Understanding is fading",
  understood: "Understood",
  human: "Written by a person",
  uncommitted: "Not committed yet",
};

const EXPLAIN: Record<State, string> = {
  unread: "No one on the team has shown they understand this AI-written code.",
  skimmed: "Someone reviewed it or took a quiz with a low score, but nobody has fully shown they understand it.",
  fading: "Someone understood it, but more than 180 days ago.",
  understood: "Someone passed a quiz, explained it or paired on it.",
  human: "Written by a person.",
  uncommitted: "Grok-map will track this line once it is committed.",
};

/**
 * Group consecutive lines with the same state and commit into spans, so the editor gets one
 * decoration (and one hover) per block instead of one per line. Lines skipped by grokmap
 * (blank lines, lone brackets) inside a block are bridged so the colour does not flicker.
 */
export function toSpans(lines: LineInfo[], maxGap = 3): Span[] {
  const spans: Span[] = [];
  for (const ln of [...lines].sort((a, b) => a.line - b.line)) {
    const last = spans[spans.length - 1];
    const by = ln.understood_by ?? [];
    if (
      last &&
      last.state === ln.state &&
      last.sha === ln.sha &&
      ln.line - last.end <= maxGap &&
      sameMembers(last.understoodBy, by)
    ) {
      last.end = ln.line;
    } else {
      spans.push({ state: ln.state, start: ln.line, end: ln.line, sha: ln.sha, agent: ln.agent, understoodBy: by });
    }
  }
  return spans;
}

function sameMembers(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((x, i) => x === b[i]);
}

export function agentName(agent: string | undefined | null): string {
  if (!agent) return "a person";
  const known: Record<string, string> = {
    claude: "Claude",
    copilot: "GitHub Copilot",
    cursor: "Cursor",
    codex: "Codex",
    aider: "Aider",
    devin: "Devin",
    gemini: "Gemini",
    crush: "Crush",
    ai: "an AI agent",
  };
  return known[agent] ?? agent;
}

/** Markdown for the hover over a span. `quizCommand` is a command: URI, or empty to leave it out. */
export function hoverMarkdown(span: Span, commits: Record<string, CommitInfo>, quizCommand = ""): string {
  const parts = [`**Grok-map · ${LABELS[span.state]}**`, "", EXPLAIN[span.state]];
  const c = span.sha ? commits[span.sha] : undefined;
  if (c) {
    const who = span.agent ? `${agentName(span.agent)} (committed by ${c.author})` : c.author;
    parts.push("", `Written by ${who} on ${c.date} in \`${span.sha}\`: ${escapeMd(c.summary)}`);
  }
  if (span.understoodBy.length) {
    parts.push("", `Understood by ${span.understoodBy.map(escapeMd).join(", ")}`);
  }
  if (quizCommand && (span.state === "unread" || span.state === "skimmed" || span.state === "fading")) {
    parts.push("", `[Quiz me on this](${quizCommand})`);
  }
  return parts.join("\n");
}

export function escapeMd(text: string): string {
  return text.replace(/([\\`*_{}[\]()#+!|<>])/g, "\\$1");
}

/** Text for the status bar item, or undefined when there is nothing to show. */
export function statusText(data: FileData): string | undefined {
  const s = data.summary;
  if (!data.tracked || !s || s.ai === 0) return undefined;
  return `Grok-map ${s.debt_pct}%`;
}

export function statusTooltip(data: FileData): string {
  const s = data.summary;
  if (!s) return "Grok-map";
  const lines = [
    `Comprehension debt ${s.debt_pct}% in this file${data.critical ? " (critical path)" : ""}`,
    `${s.ai} of ${s.lines} lines written by AI: ${s.unread} unread, ${s.skimmed} skimmed, ${s.fading} fading, ${s.understood} understood`,
  ];
  const people = Object.entries(s.people);
  lines.push(people.length ? `Understood by: ${people.map(([p, n]) => `${p} (${n})`).join(", ")}` : "Nobody has shown they understand the AI-written code here yet.");
  return lines.join("\n");
}
