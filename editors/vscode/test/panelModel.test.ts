import assert from "node:assert/strict";
import { test } from "node:test";
import {
  StatusJson,
  QuizTarget,
  availableAssistants,
  averageScore,
  codeListing,
  dashboard,
  gradePrompt,
  handoffPrompt,
  markArgs,
  parseJsonReply,
  questionCount,
  questionPrompt,
  readGrades,
  readQuestions,
  riskyFiles,
  verdict,
} from "../src/panelModel";

const stats = (ai: number, unread: number, skimmed = 0, fading = 0, extra: Partial<StatusJson["total"]> = {}) => ({
  lines: ai + 10,
  human: 10,
  ai,
  understood: ai - unread - skimmed - fading,
  fading,
  skimmed,
  unread,
  debt_pct: ai ? Math.round((100 * (unread + 0.5 * (skimmed + fading))) / (ai + 10)) : 0,
  tools: {},
  people: {},
  ...extra,
});

const status: StatusJson = {
  repo: "shop",
  total: stats(100, 40, 10, 0, { tools: { claude: 70, copilot: 30 }, people: { "b@x": 5, "a@x": 20 } }),
  files: {
    "src/a.py": stats(30, 30),
    "src/deep/b.py": stats(40, 5, 20),
    "c.py": stats(20, 0),
    "README.md": stats(0, 0),
    "src/d.py": stats(10, 5, 0, 5),
  },
};

test("dashboard totals, people and tools are sorted biggest first", () => {
  const d = dashboard(status);
  assert.equal(d.ai, 100);
  assert.equal(d.understoodPct, 50);
  assert.equal(d.open, 50);
  assert.deepEqual(d.people.map((p) => p.name), ["a@x", "b@x"]);
  assert.deepEqual(d.tools.map((t) => t.name), ["Claude", "GitHub Copilot"]);
});

test("risky files: only files with open lines, unread weighs more than skimmed", () => {
  const { list, more } = riskyFiles(status, 2);
  assert.deepEqual(list.map((f) => f.path), ["src/a.py", "src/deep/b.py"]);
  assert.equal(more, 1); // src/d.py
  assert.equal(list[1].name, "b.py");
  assert.equal(list[1].dir, "src/deep");
  assert.equal(list[0].open, 30);
  assert.equal(riskyFiles(status).list.find((f) => f.path === "c.py"), undefined);
});

const target: QuizTarget = {
  path: "src/retry.py",
  ranges: [
    [3, 5],
    [9, 9],
  ],
  tools: ["claude"],
  lines: { "3": "def f(x):", "4": "    if not x:", "5": "        return 0", "9": "    return x * 2" },
};

test("code listing numbers the lines like the CLI brief", () => {
  const text = codeListing([target]);
  assert.match(text, /### src\/retry.py \(lines 3-5,9, written by Claude\)/);
  assert.match(text, /3 \| def f\(x\):/);
  assert.match(text, /9 \| {5}return x \* 2/);
  assert.match(codeListing([target], 20), /cut here/);
});

test("question count follows the CLI rule", () => {
  assert.equal(questionCount([target]), 3);
  const big = { ...target, lines: Object.fromEntries(Array.from({ length: 400 }, (_, i) => [String(i + 1), "x = 1"])) };
  assert.equal(questionCount([big]), 6);
});

test("prompts ask for JSON and carry the code and answers", () => {
  const qp = questionPrompt([target], 3);
  assert.match(qp, /exactly 3 questions/);
  assert.match(qp, /"questions"/);
  assert.match(qp, /def f\(x\)/);
  const gp = gradePrompt([target], [{ question: "What if x is empty?", lines: "4-5", topic: "" }], ["returns 0"]);
  assert.match(gp, /Q1 \(lines 4-5\): What if x is empty\?\nA1: returns 0/);
  assert.match(gp, /exactly 1 grades/);
});

test("reads JSON out of chatty or fenced model replies", () => {
  assert.deepEqual(parseJsonReply('Sure!\n```json\n{"questions":[{"question":"Why?"}]}\n```\nGood luck'), {
    questions: [{ question: "Why?" }],
  });
  assert.throws(() => parseJsonReply("no json here"), /did not reply with JSON/);
});

test("questions: accepts strings, drops empties, caps the count", () => {
  const qs = readQuestions({ questions: ["Why A?", { question: " Why B? ", lines: "3-5", topic: "B" }, { question: "" }, "Why C?", "Why D?"] }, 3);
  assert.deepEqual(
    qs.map((q) => q.question),
    ["Why A?", "Why B?", "Why C?"],
  );
  assert.equal(qs[1].lines, "3-5");
  assert.throws(() => readQuestions({ questions: [] }, 3), /no questions/);
});

test("grades snap to 0 / 0.5 / 1, fill missing ones with 0, and average", () => {
  const g = readGrades({ grades: [{ score: 0.9, feedback: "ok", answer: "a" }, { score: "0.4" }, { score: 60 }] }, 4);
  assert.deepEqual(
    g.map((x) => x.score),
    [1, 0.5, 0.5, 0],
  );
  assert.equal(averageScore(g), 0.5);
  assert.equal(verdict(0.67), "partly");
  assert.equal(verdict(0.7), "understood");
  assert.equal(verdict(0), "not-yet");
});

test("mark arguments cover exactly the quizzed lines", () => {
  assert.deepEqual(markArgs([target], 0.833, "panel"), [
    "mark",
    "src/retry.py:3-5,9",
    "--score",
    "0.83",
    "--method",
    "quiz",
    "--note",
    "panel",
  ]);
});

test("assistants: installed ones, plus Cursor's own chat in Cursor", () => {
  const ids = (xs: { id: string }[]) => xs.map((x) => x.id);
  assert.deepEqual(ids(availableAssistants((id) => id === "anthropic.claude-code", "Visual Studio Code")), ["anthropic.claude-code"]);
  assert.deepEqual(ids(availableAssistants(() => false, "Cursor")), ["cursor"]);
  assert.match(handoffPrompt("# grokmap quiz brief\n..."), /record_understanding[\s\S]*# grokmap quiz brief/);
});
