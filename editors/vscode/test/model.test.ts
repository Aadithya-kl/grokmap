import assert from "node:assert/strict";
import { test } from "node:test";
import { FileData, LineInfo, hoverMarkdown, statusText, toSpans } from "../src/model";

const L = (line: number, state: LineInfo["state"], sha = "aaa", extra: Partial<LineInfo> = {}): LineInfo => ({ line, state, sha, ...extra });

test("consecutive lines with the same state and commit become one span", () => {
  const spans = toSpans([L(1, "unread"), L(2, "unread"), L(4, "unread"), L(5, "understood")]);
  assert.deepEqual(
    spans.map((s) => [s.state, s.start, s.end]),
    [
      ["unread", 1, 4],
      ["understood", 5, 5],
    ],
  );
});

test("a big gap or a different commit starts a new span", () => {
  const spans = toSpans([L(1, "unread"), L(9, "unread"), L(10, "unread", "bbb")]);
  assert.equal(spans.length, 3);
});

test("lines understood by different people are kept apart", () => {
  const spans = toSpans([
    L(1, "understood", "aaa", { understood_by: ["ana"] }),
    L(2, "understood", "aaa", { understood_by: ["bo"] }),
  ]);
  assert.equal(spans.length, 2);
});

test("hover names the agent, the commit and offers a quiz only when useful", () => {
  const commits = { aaa: { author: "Priya", date: "2026-08-24", summary: "Payments [retry]", agent: "claude" } };
  const unread = hoverMarkdown(toSpans([L(3, "unread", "aaa", { agent: "claude" })])[0], commits, "command:grokmap.quiz");
  assert.match(unread, /Nobody has checked this/);
  assert.match(unread, /Claude \(committed by Priya\)/);
  assert.match(unread, /Payments \\\[retry\\\]/);
  assert.match(unread, /\[Quiz me on this\]\(command:grokmap\.quiz\)/);
  const ok = hoverMarkdown(toSpans([L(3, "understood", "aaa", { agent: "claude", understood_by: ["ana@x.io"] })])[0], commits, "command:x");
  assert.doesNotMatch(ok, /Quiz me/);
  assert.match(ok, /Understood by ana@x\.io/);
});

test("status bar only appears for files with AI-written code", () => {
  const base: FileData = { path: "a.py", tracked: true, lines: [] };
  const summary = { lines: 10, human: 4, ai: 6, understood: 2, fading: 0, skimmed: 0, unread: 4, debt_pct: 40, tools: {}, people: {} };
  assert.equal(statusText({ ...base, summary }), "Grok-map 40%");
  assert.equal(statusText({ ...base, summary: { ...summary, ai: 0 } }), undefined);
  assert.equal(statusText({ ...base, tracked: false }), undefined);
});
