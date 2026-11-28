// Pure logic for the Grok-map panel: no `vscode` import, so it can be unit-tested with node.

export interface Stats {
  lines: number;
  human: number;
  ai: number;
  understood: number;
  fading: number;
  skimmed: number;
  unread: number;
  debt_lines?: number;
  debt_pct: number;
  ai_pct?: number;
  tools: Record<string, number>;
  people: Record<string, number>;
}

/** What `grokmap status --json` prints. */
export interface StatusJson {
  repo: string;
  head?: string;
  total: Stats;
  files: Record<string, Stats>;
}

export interface RiskyFile {
  path: string;
  name: string;
  dir: string;
  ai: number;
  open: number; // AI lines nobody fully understands (unread + skimmed + fading)
  debtPct: number;
  understood: number;
  fading: number;
  skimmed: number;
  unread: number;
}

export interface Dashboard {
  repo: string;
  lines: number;
  ai: number;
  aiPct: number;
  understood: number;
  fading: number;
  skimmed: number;
  unread: number;
  understoodPct: number; // of AI-written lines
  debtPct: number;
  open: number;
  people: { name: string; lines: number }[];
  tools: { name: string; lines: number }[];
  risky: RiskyFile[];
  riskyMore: number; // files with open lines beyond the ones listed
}

const TOOL_NAMES: Record<string, string> = {
  claude: "Claude",
  copilot: "GitHub Copilot",
  cursor: "Cursor",
  codex: "Codex",
  aider: "Aider",
  devin: "Devin",
  gemini: "Gemini",
  crush: "Crush",
  ai: "Other AI",
};

export function toolName(id: string): string {
  return TOOL_NAMES[id] ?? id;
}

function pct(part: number, whole: number): number {
  return whole > 0 ? Math.round((1000 * part) / whole) / 10 : 0;
}

function sortedEntries(rec: Record<string, number> | undefined): [string, number][] {
  return Object.entries(rec ?? {}).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

export function openLines(s: Stats): number {
  return s.unread + s.skimmed + s.fading;
}

/** Files with the most AI-written lines nobody fully understands, worst first. */
export function riskyFiles(status: StatusJson, limit = 8): { list: RiskyFile[]; more: number } {
  const all: RiskyFile[] = [];
  for (const [path, s] of Object.entries(status.files ?? {})) {
    const open = openLines(s);
    if (open <= 0) continue;
    const slash = path.lastIndexOf("/");
    all.push({
      path,
      name: path.slice(slash + 1),
      dir: slash >= 0 ? path.slice(0, slash) : "",
      ai: s.ai,
      open,
      debtPct: s.debt_pct,
      understood: s.understood,
      fading: s.fading,
      skimmed: s.skimmed,
      unread: s.unread,
    });
  }
  // weight unread fully, skimmed and fading partly, the same way the debt score does
  const weight = (f: RiskyFile) => f.unread + 0.5 * f.skimmed + 0.5 * f.fading;
  all.sort((a, b) => weight(b) - weight(a) || b.ai - a.ai || a.path.localeCompare(b.path));
  return { list: all.slice(0, limit), more: Math.max(0, all.length - limit) };
}

export function dashboard(status: StatusJson, limit = 8): Dashboard {
  const t = status.total;
  const { list, more } = riskyFiles(status, limit);
  return {
    repo: status.repo,
    lines: t.lines,
    ai: t.ai,
    aiPct: t.ai_pct ?? pct(t.ai, t.lines),
    understood: t.understood,
    fading: t.fading,
    skimmed: t.skimmed,
    unread: t.unread,
    understoodPct: pct(t.understood, t.ai),
    debtPct: t.debt_pct,
    open: openLines(t),
    people: sortedEntries(t.people).map(([name, lines]) => ({ name, lines })),
    tools: sortedEntries(t.tools).map(([name, lines]) => ({ name: toolName(name), lines })),
    risky: list,
    riskyMore: more,
  };
}

// ---------------------------------------------------------------- quiz

/** One file's code to quiz on, as `grokmap quiz --format json` prints it. */
export interface QuizTarget {
  path: string;
  ranges: [number, number][];
  tools: string[];
  lines: Record<string, string>;
}

export interface QuizJson {
  who: string;
  truncated: boolean;
  targets: QuizTarget[];
}

export interface Question {
  question: string;
  lines: string; // e.g. "12-30", for the reader
  topic: string;
}

export interface Grade {
  score: number; // 0, 0.5 or 1
  feedback: string;
  answer: string; // a model answer, shown after grading
}

export function rangesText(ranges: [number, number][]): string {
  return ranges.map(([a, b]) => (a === b ? `${a}` : `${a}-${b}`)).join(",");
}

export function totalLines(targets: QuizTarget[]): number {
  return targets.reduce((n, t) => n + Object.keys(t.lines).length, 0);
}

/** Same rule as the CLI's quiz brief: at least 3, one more per 80 lines, at most 6. */
export function questionCount(targets: QuizTarget[], minimum = 3): number {
  return Math.max(minimum, Math.min(6, 2 + Math.floor(totalLines(targets) / 80)));
}

/** The code with line numbers, the way the quiz brief shows it. Cut at `maxChars`. */
export function codeListing(targets: QuizTarget[], maxChars = 24000): string {
  const out: string[] = [];
  let size = 0;
  for (const t of targets) {
    out.push(`### ${t.path} (lines ${rangesText(t.ranges)}${t.tools.length ? `, written by ${t.tools.map(toolName).join(", ")}` : ""})`);
    for (const [lo, hi] of t.ranges) {
      out.push("```");
      const width = String(hi).length;
      for (let n = lo; n <= hi; n++) {
        const text = t.lines[String(n)];
        if (text === undefined) continue;
        const row = `${String(n).padStart(width)} | ${text}`;
        size += row.length + 1;
        if (size > maxChars) {
          out.push("```", "(cut here to keep the quiz short)");
          return out.join("\n");
        }
        out.push(row);
      }
      out.push("```");
    }
  }
  return out.join("\n");
}

export function questionPrompt(targets: QuizTarget[], n: number): string {
  return [
    "You are writing a short comprehension quiz for a developer about code an AI wrote in their project.",
    "The goal: check they understand it well enough to debug it at 2am without an AI.",
    "",
    `Write exactly ${n} questions. Good questions ask why and what-if, not trivia:`,
    '- "What happens if X is empty, missing or huge?"',
    '- "Why is this done before that?"',
    '- "A user reports <symptom>. Where would you look first?"',
    '- "What would break if this line were removed?"',
    "Avoid questions answerable by re-reading a name. Do not quote the code back or hint at the answer.",
    "Each question must be answerable in two or three sentences. Cover different parts of the code.",
    "",
    'Reply with JSON only, no prose and no code fence: {"questions":[{"question":"...","lines":"12-30","topic":"two to four words"}]}',
    "",
    "The code:",
    codeListing(targets),
  ].join("\n");
}

export function gradePrompt(targets: QuizTarget[], questions: Question[], answers: string[]): string {
  const qa = questions
    .map((q, i) => `Q${i + 1} (lines ${q.lines}): ${q.question}\nA${i + 1}: ${answers[i]?.trim() || "(no answer)"}`)
    .join("\n\n");
  return [
    "You are grading a developer's answers to a comprehension quiz about code in their project.",
    "Grade each answer: 1 = correct and explains why; 0.5 = partly right or vague; 0 = wrong, empty or \"I don't know\".",
    "Be fair but strict: a confident answer that is wrong scores 0. Judge only against the code below.",
    "For each, give one or two sentences of feedback addressed to the developer, and a short model answer.",
    "",
    'Reply with JSON only, no prose and no code fence: {"grades":[{"score":1,"feedback":"...","answer":"..."}]}',
    `There must be exactly ${questions.length} grades, in order.`,
    "",
    "The code:",
    codeListing(targets),
    "",
    "Questions and answers:",
    qa,
  ].join("\n");
}

/** Pull the first JSON object out of a model reply (it may wrap it in a fence or add a sentence). */
export function parseJsonReply(text: string): unknown {
  const cleaned = text.replace(/```(?:json)?/gi, "");
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start < 0 || end <= start) throw new Error("the model did not reply with JSON");
  return JSON.parse(cleaned.slice(start, end + 1));
}

function str(v: unknown): string {
  return typeof v === "string" ? v.trim() : v === undefined || v === null ? "" : String(v).trim();
}

export function readQuestions(reply: unknown, n: number): Question[] {
  const list = (reply as { questions?: unknown[] })?.questions;
  if (!Array.isArray(list)) throw new Error("the model's reply had no questions");
  const qs = list
    .map((q) => (typeof q === "string" ? { question: q } : (q as Record<string, unknown>)))
    .map((q) => ({ question: str(q.question), lines: str(q.lines), topic: str(q.topic) }))
    .filter((q) => q.question.length > 0);
  if (!qs.length) throw new Error("the model's reply had no questions");
  return qs.slice(0, Math.max(n, 1));
}

export function readGrades(reply: unknown, n: number): Grade[] {
  const list = (reply as { grades?: unknown[] })?.grades;
  if (!Array.isArray(list)) throw new Error("the model's reply had no grades");
  const grades: Grade[] = [];
  for (let i = 0; i < n; i++) {
    const g = (list[i] ?? {}) as Record<string, unknown>;
    const raw = Number(g.score);
    // snap to the 0 / 0.5 / 1 scale the rubric uses
    const score = Number.isFinite(raw) ? Math.round(Math.min(1, Math.max(0, raw > 1 ? raw / 100 : raw)) * 2) / 2 : 0;
    grades.push({ score, feedback: str(g.feedback), answer: str(g.answer) });
  }
  return grades;
}

export function averageScore(grades: Grade[]): number {
  if (!grades.length) return 0;
  return Math.round((100 * grades.reduce((s, g) => s + g.score, 0)) / grades.length) / 100;
}

export type Verdict = "understood" | "partly" | "not-yet";

export function verdict(score: number, passScore = 0.7): Verdict {
  if (score >= passScore) return "understood";
  if (score > 0) return "partly";
  return "not-yet";
}

/** Arguments for `grokmap mark` that record the result for exactly the quizzed lines. */
export function markArgs(targets: QuizTarget[], score: number, note: string): string[] {
  return [
    "mark",
    ...targets.map((t) => `${t.path}:${rangesText(t.ranges)}`),
    "--score",
    score.toFixed(2),
    "--method",
    "quiz",
    "--note",
    note,
  ];
}

// ---------------------------------------------------------------- hand-off

export interface Assistant {
  id: string; // extension id, or "cursor" / "copy"
  name: string;
  /** Commands to try in order; the first that runs wins. `chat` ones get the prompt as a query. */
  commands: { command: string; chat?: boolean }[];
}

export const ASSISTANTS: Assistant[] = [
  { id: "anthropic.claude-code", name: "Claude Code", commands: [{ command: "claude-vscode.editor.open" }, { command: "claude-vscode.focus" }] },
  { id: "github.copilot-chat", name: "Copilot Chat", commands: [{ command: "workbench.action.chat.open", chat: true }] },
  {
    id: "kilocode.kilo-code",
    name: "Kilo Code",
    commands: [{ command: "kilo-code.SidebarProvider.focus" }, { command: "workbench.view.extension.kilo-code-ActivityBar" }],
  },
  { id: "saoudrizwan.claude-dev", name: "Cline", commands: [{ command: "claude-dev.SidebarProvider.focus" }] },
  { id: "rooveterinaryinc.roo-cline", name: "Roo Code", commands: [{ command: "roo-cline.SidebarProvider.focus" }] },
];

export const CURSOR: Assistant = { id: "cursor", name: "Cursor chat", commands: [{ command: "composer.newAgentChat" }] };

/** The assistants worth offering, given installed extension ids and the editor's name. */
export function availableAssistants(installed: (id: string) => boolean, appName: string): Assistant[] {
  const list = ASSISTANTS.filter((a) => installed(a.id));
  if (/cursor/i.test(appName)) list.unshift(CURSOR);
  return list;
}

export function handoffPrompt(brief: string): string {
  return [
    "Quiz me on this code using the Grok-map instructions below, one question at a time.",
    "When we're done, record my score with the grokmap MCP tool record_understanding (or run the grokmap mark command shown).",
    "",
    brief.trim(),
  ].join("\n");
}
