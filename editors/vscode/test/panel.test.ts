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
    window: {
      activeTextEditor: undefined,
      showInformationMessage: async () => undefined,
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
  return { repo, view, context, clipboard, prompts, send: (m: unknown) => receive(m), until, restore: () => (M._load = realLoad) };
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
    const asking = await t.until((s) => s.quiz?.phase === "asking", "questions");
    assert.equal(asking.quiz.questions.length, 3);
    assert.equal(asking.quiz.model, "Fake model");
    assert.match(prompts[0], new RegExp(file!.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));

    t.send({ type: "answers", answers: ["It retries a decline.", "To spread load.", "The charge call."] });
    const done = await t.until((s) => s.quiz?.phase === "done" && !!s.quiz.saved && s.dash?.understood > before, "the saved result");
    assert.equal(done.quiz.score, 0.83);
    assert.equal(done.quiz.verdict, "understood");
    assert.match(done.quiz.saved, /Saved to \.grokmap\/ledger\.jsonl/);

    const who = execFileSync(command.split(" ")[0], [...command.split(" ").slice(1), "who", file!], { cwd: t.repo, encoding: "utf8" });
    assert.match(who, /understands/);
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
    await t.until((s) => s.quiz?.phase === "choose", "the hand-off choice");
    t.send({ type: "handoff", id: "copy" });
    for (let i = 0; i < 100 && !t.clipboard.length; i++) await new Promise((r) => setTimeout(r, 50));
    assert.match(t.clipboard[0] ?? "", /record_understanding/);
    assert.match(t.clipboard[0] ?? "", /grokmap quiz brief/);
  } finally {
    t.restore();
  }
});
