// Drives the Grok-map panel against a minimal stand-in for the `vscode` API, the real grokmap
// CLI and a fake language model. Skipped unless GROKMAP_TEST_REPO and GROKMAP_TEST_FILE are set
// (CI sets both, using the demo repository). Works on a copy, because the quiz writes the ledger.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import Module from "node:module";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";

const source = process.env.GROKMAP_TEST_REPO;
const file = process.env.GROKMAP_TEST_FILE;
const command = process.env.GROKMAP_COMMAND ?? "grokmap";

type Msg = { type: string; state?: Record<string, any> };

function setup(models: unknown[]) {
  const repo = fs.mkdtempSync(path.join(os.tmpdir(), "grokmap-panel-"));
  fs.cpSync(source!, repo, { recursive: true });
  const posted: Msg[] = [];
  const clipboard: string[] = [];
  const prompts: string[] = [];
  const confirm: string[] = [];
  const errors: string[] = [];
  let receive: (m: unknown) => void = () => {};
  const global = new Map<string, unknown>();
  class CancellationTokenSource {
    token = { isCancellationRequested: false };
    cancel() {}
    dispose() {}
  }
  const vscode = {
    Uri: {
      joinPath: (_b: unknown, ...p: string[]) => ({ fsPath: p.join("/"), toString: () => p.join("/") }),
      file: (p: string) => ({ fsPath: p, scheme: "file" }),
      parse: (s: string) => ({ s }),
    },
    ViewColumn: { Active: -1, Beside: -2 },
    ConfigurationTarget: { Global: 1 },
    CancellationTokenSource,
    CancellationError: class extends Error {},
    LanguageModelError: class extends Error {},
    LanguageModelChatMessage: { User: (content: string) => ({ content }) },
    QuickPickItemKind: { Separator: -1 },
    window: {
      activeTextEditor: undefined,
      // modal confirmations: answer with the button the test queued, else dismiss
      showInformationMessage: async (_m: string, ...rest: unknown[]) => {
        const buttons = rest.filter((x) => typeof x === "string") as string[];
        return confirm.length ? (buttons.includes(confirm[0]) ? confirm.shift() : undefined) : undefined;
      },
      showErrorMessage: async (m: string) => void errors.push(m),
      setStatusBarMessage: () => ({ dispose() {} }),
    },
    workspace: {
      workspaceFolders: [{ uri: { scheme: "file", fsPath: repo }, name: path.basename(repo) }],
      getConfiguration: () => ({ get: (k: string, d: unknown) => (k === "command" ? command : d), update: async () => {} }),
    },
    extensions: { getExtension: () => undefined },
    env: { appName: "Visual Studio Code", clipboard: { writeText: async (t: string) => void clipboard.push(t) } },
    commands: { executeCommand: async () => undefined },
    lm: { selectChatModels: async () => models },
  };
  // load the panel fresh, so it binds to this test's stand-in
  for (const key of Object.keys(require.cache)) if (/[\\/]out[\\/]src[\\/]/.test(key)) delete require.cache[key];
  const M = Module as unknown as { _load: (req: string, ...rest: unknown[]) => unknown };
  const realLoad = M._load;
  M._load = (req: string, ...rest: unknown[]) => (req === "vscode" ? vscode : realLoad(req, ...rest));

  const webview = {
    options: {},
    html: "",
    cspSource: "vscode-resource:",
    asWebviewUri: (u: { fsPath: string }) => u.fsPath,
    onDidReceiveMessage: (fn: (m: unknown) => void) => ((receive = fn), { dispose() {} }),
    postMessage: async (m: Msg) => void posted.push(JSON.parse(JSON.stringify(m))),
  };
  const view = { webview, visible: true, onDidDispose: () => ({ dispose() {} }), onDidChangeVisibility: () => ({ dispose() {} }) };
  const context = {
    extensionUri: {},
    subscriptions: [],
    globalState: { get: (k: string, d?: unknown) => (global.has(k) ? global.get(k) : d), update: async (k: string, v: unknown) => void global.set(k, v) },
  };
  const last = () => posted[posted.length - 1]?.state ?? {};
  const until = async (ok: (s: Record<string, any>) => boolean, what: string) => {
    for (let i = 0; i < 400; i++) {
      if (ok(last())) return last();
      await new Promise((r) => setTimeout(r, 50));
    }
    throw new Error(`timed out waiting for ${what}; last state: ${JSON.stringify(last()).slice(0, 600)}`);
  };
  return { repo, view, context, clipboard, prompts, confirm, errors, send: (m: unknown) => receive(m), until, restore: () => (M._load = realLoad) };
}

function fakeModel(prompts: string[]) {
  return {
    id: "fake",
    name: "Fake model",
    async sendRequest(messages: { content: string }[]) {
      const prompt = messages[0].content;
      prompts.push(prompt);
      const reply = prompt.includes('"questions"')
        ? 'Here you go:\n```json\n{"questions":[{"question":"What happens on a declined card?","lines":"1-5","topic":"Declines"},{"question":"Why the jitter?","lines":"6-9","topic":"Backoff"},{"question":"Where would you look for a double charge?","lines":"9","topic":"Idempotency"}]}\n```'
        : '{"grades":[{"score":1,"feedback":"Right.","answer":"It retries."},{"score":1,"feedback":"Yes.","answer":"Spreads load."},{"score":0.5,"feedback":"Partly.","answer":"The charge call."}]}';
      return {
        text: (async function* () {
          yield reply.slice(0, 10);
          yield reply.slice(10);
        })(),
      };
    },
  };
}

test("panel: dashboard, in-panel quiz with a model, result recorded in the ledger", { skip: !source || !file }, async () => {
  const prompts: string[] = [];
  const t = setup([fakeModel(prompts)]);
  try {
    const { GrokmapPanel } = await import("../src/panel");
    const panel = new GrokmapPanel(t.context as never, async () => undefined);
    panel.resolveWebviewView(t.view as never);
    const ready = await t.until((s) => s.phase === "ready", "the dashboard");
    assert.ok(ready.dash.ai > 0, "demo repository should have AI-written lines");
    assert.ok(ready.dash.risky.some((f: { path: string }) => f.path === file), `${file} should need attention`);
    const before = ready.dash.understood;

    t.send({ type: "quiz", path: file });
    const start = await t.until((s) => s.quiz?.phase === "start", "the start screen");
    assert.equal(prompts.length, 0, "nothing goes to the model before Start");
    assert.ok(start.quiz.files.some((f: { path: string }) => f.path === file));
    assert.equal(start.quiz.hasModel, true);

    t.send({ type: "begin", depth: "quick", mode: "quiz" });
    const asking = await t.until((s) => s.quiz?.phase === "asking", "questions");
    assert.equal(asking.quiz.questions.length, 3);
    assert.equal(asking.quiz.model, "Fake model");
    assert.match(prompts[0], new RegExp(file!.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));

    t.send({ type: "answers", answers: ["It retries a decline.", "To spread load.", "The charge call."] });
    const done = await t.until((s) => s.quiz?.phase === "done" && !!s.quiz.saved && s.dash?.understood > before, "the saved result");
    assert.equal(done.quiz.score, 0.83);
    assert.equal(done.quiz.verdict, "understood");
    assert.match(done.quiz.saved, /^Saved to the ledger for \d+ lines\.$/);

    // commit only the ledger, as the button does
    fs.writeFileSync(path.join(t.repo, "unrelated.txt"), "not part of the commit\n");
    t.send({ type: "commitLedger" });
    const committed = await t.until((s) => !!s.quiz?.committed, "the commit");
    assert.match(committed.quiz.committed, /^Committed [0-9a-f]+ on /);
    const last = execFileSync("git", ["show", "--stat", "--format=%s", "HEAD"], { cwd: t.repo, encoding: "utf8" });
    assert.match(last, /^grokmap: understanding of /);
    assert.match(last, /\.grokmap\/ledger\.jsonl/);
    assert.doesNotMatch(last, /unrelated/);

    const who = execFileSync(command.split(" ")[0], [...command.split(" ").slice(1), "who", file!], { cwd: t.repo, encoding: "utf8" });
    assert.match(who, /understands/);
  } finally {
    t.restore();
  }
});

test("panel: explain it instead, graded and recorded as an explanation", { skip: !source || !file }, async () => {
  const prompts: string[] = [];
  const model = {
    id: "fake",
    name: "Fake model",
    async sendRequest(messages: { content: string }[]) {
      prompts.push(messages[0].content);
      const reply = '{"score":1,"feedback":"Clear and complete.","missing":[],"answer":"It retries with backoff."}';
      return { text: (async function* () { yield reply; })() };
    },
  };
  const t = setup([model]);
  try {
    const { GrokmapPanel } = await import("../src/panel");
    const panel = new GrokmapPanel(t.context as never, async () => undefined);
    panel.resolveWebviewView(t.view as never);
    await t.until((s) => s.phase === "ready", "the dashboard");
    t.send({ type: "quiz", path: file });
    await t.until((s) => s.quiz?.phase === "start", "the start screen");
    t.send({ type: "begin", depth: "quick", mode: "explain" });
    await t.until((s) => s.quiz?.phase === "explain", "the explain screen");
    t.send({ type: "explanation", text: "It calls the payment client and retries on network errors with exponential backoff, so a flaky API doesn't fail the order." });
    const done = await t.until((s) => s.quiz?.phase === "done" && !!s.quiz.saved, "the result");
    assert.equal(done.quiz.score, 1);
    assert.match(prompts[0], /Their explanation:/);
    const ledger = fs.readFileSync(path.join(t.repo, ".grokmap", "ledger.jsonl"), "utf8");
    assert.match(ledger, /"method": ?"explain"/);
  } finally {
    t.restore();
  }
});

test("panel: this branch, quiz before push, mark as reviewed, ignore", { skip: !source || !file }, async () => {
  const prompts: string[] = [];
  const t = setup([fakeModel(prompts)]);
  const g = (...args: string[]) => execFileSync("git", args, { cwd: t.repo, encoding: "utf8" });
  try {
    // a feature branch with one AI-written commit
    g("switch", "-q", "-c", "feat/limits");
    fs.appendFileSync(path.join(t.repo, file!), "\n\ndef limit(n):\n    if n < 0:\n        raise ValueError(n)\n    return min(n, 5)\n");
    g("commit", "-qam", "limit retries\n\nCo-Authored-By: Claude <noreply@anthropic.com>");

    const { GrokmapPanel } = await import("../src/panel");
    const panel = new GrokmapPanel(t.context as never, async () => undefined);
    panel.resolveWebviewView(t.view as never);
    const ready = await t.until((s) => s.phase === "ready" && !!s.branch, "the branch card");
    assert.equal(ready.branch.name, "feat/limits");
    assert.equal(ready.branch.base, "main");
    assert.ok(ready.branch.open >= 4);
    assert.equal(ready.codeOnly, true);

    t.send({ type: "quiz", path: `diff:${ready.branch.base}` });
    const start = await t.until((s) => s.quiz?.phase === "start", "the branch quiz start screen");
    assert.equal(start.quiz.title, "This branch");
    assert.deepEqual(
      start.quiz.files.map((f: { path: string }) => f.path),
      [file],
    );
    t.send({ type: "closeQuiz" });

    // mark as reviewed: asks first, then records a review (skimmed)
    t.confirm.push("I reviewed it");
    const unreadBefore = ready.dash.unread;
    t.send({ type: "review", path: file });
    await t.until((s) => s.dash && s.dash.skimmed > 0 && s.dash.unread < unreadBefore, "the review to count as skimmed");
    assert.match(fs.readFileSync(path.join(t.repo, ".grokmap", "ledger.jsonl"), "utf8"), /"method": ?"review"/);

    // ignore: asks first, writes .grokmap.toml, and the file drops out
    const dir = file!.split("/").slice(0, -1).join("/");
    t.confirm.push("Ignore");
    t.send({ type: "ignore", path: dir, folder: true });
    await t.until((s) => s.dash && !s.dash.risky.some((f: { path: string }) => f.path.startsWith(dir + "/")), "the folder to drop out");
    assert.match(fs.readFileSync(path.join(t.repo, ".grokmap.toml"), "utf8"), new RegExp(`exclude = \\["${dir.replace(/[/.]/g, "\\$&")}/\\*\\*"\\]`));
    assert.deepEqual(t.errors, []);
  } finally {
    t.restore();
  }
});

test("panel: without a model it offers the hand-off and copies a brief", { skip: !source || !file }, async () => {
  const t = setup([]);
  try {
    const { GrokmapPanel } = await import("../src/panel");
    const panel = new GrokmapPanel(t.context as never, async () => undefined);
    panel.resolveWebviewView(t.view as never);
    await t.until((s) => s.phase === "ready", "the dashboard");
    t.send({ type: "quiz", path: file });
    await t.until((s) => s.quiz?.phase === "start" && s.quiz.hasModel === false, "the start screen");
    t.send({ type: "begin", depth: "quick", mode: "quiz" });
    await t.until((s) => s.quiz?.phase === "choose", "the hand-off choice");
    t.send({ type: "handoff", id: "copy" });
    for (let i = 0; i < 100 && !t.clipboard.length; i++) await new Promise((r) => setTimeout(r, 50));
    assert.match(t.clipboard[0] ?? "", /record_understanding/);
    assert.match(t.clipboard[0] ?? "", /grokmap quiz brief/);
  } finally {
    t.restore();
  }
});
