import assert from "node:assert/strict";
import { test } from "node:test";
import {
  StatusJson,
  QuizTarget,
  availableAssistants,
  averageScore,
  commitMessage,
  enforceBlanks,
  explainPrompt,
  isBlank,
  readExplainGrade,
  trendView,
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

test("question count: quick is 3, thorough scales from 4 to 6 with size", () => {
  assert.equal(questionCount([target], "quick"), 3);
  assert.equal(questionCount([target], "thorough"), 4);
  const big = { ...target, lines: Object.fromEntries(Array.from({ length: 400 }, (_, i) => [String(i + 1), "x = 1"])) };
  assert.equal(questionCount([big], "quick"), 3);
  assert.equal(questionCount([big], "thorough"), 6);
});

test("blank answers score 0 whatever the model says", () => {
  for (const a of ["", "  ", "I don't know", "i dont know.", "IDK", "no idea", "?"]) assert.ok(isBlank(a), a);
  assert.ok(!isBlank("It retries on errors"));
  const g = enforceBlanks(
    [
      { score: 1, feedback: "", answer: "a" },
      { score: 1, feedback: "ok", answer: "b" },
    ],
    ["", "It doubles the delay"],
  );
  assert.deepEqual(
    g.map((x) => x.score),
    [0, 1],
  );
  assert.equal(g[0].feedback, "Not answered.");
});

test("explain it instead: prompt, grade and a floor for one-liners", () => {
  assert.match(explainPrompt([target], "It doubles x unless empty"), /Their explanation:\nIt doubles x unless empty/);
  const g = readExplainGrade({ score: 1, feedback: "Good", missing: ["edge case", ""], answer: "x" }, "It returns 0 for empty input and doubles x otherwise, because…");
  assert.equal(g.score, 1);
  assert.deepEqual(g.missing, ["edge case"]);
  assert.equal(readExplainGrade({ score: 1 }, "it works").score, 0);
});

test("commit message names the files and the score", () => {
  assert.equal(commitMessage([target], "quiz", 0.83), "grokmap: understanding of retry.py (quiz, 83%)");
  assert.equal(commitMessage([target, target, target], "explain", 0.5), "grokmap: understanding of 3 files (explanation, 50%)");
});

test("trend: last periods, AI summed across tools, short labels", () => {
  const t = trendView(
    {
      by: "week",
      summary: { human: 0, ai: 0, ai_pct: 0, tools: {} },
      periods: [
        { start: "2026-08-03", human: 10, tools: {} },
        { start: "2026-08-10", human: 5, tools: { claude: 20, copilot: 5 } },
        { start: "2026-08-17", human: 0, tools: { cursor: 15 } },
      ],
    },
    2,
  )!;
  assert.deepEqual(
    t.periods.map((p) => [p.label, p.ai, p.human]),
    [
      ["Aug 10", 25, 5],
      ["Aug 17", 15, 0],
    ],
  );
  assert.equal(t.aiPct, 89);
  assert.equal(trendView({ by: "month", summary: { human: 0, ai: 0, ai_pct: 0, tools: {} }, periods: [] }), undefined);
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
