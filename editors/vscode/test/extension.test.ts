// Drives the real extension against a minimal stand-in for the `vscode` API and the real
// grokmap CLI. Skipped unless GROKMAP_TEST_REPO points at a repository and GROKMAP_TEST_FILE
// at a file in it with AI-written lines (CI sets both, using the demo repository).
import assert from "node:assert/strict";
import * as fs from "node:fs";
import Module from "node:module";
import * as path from "node:path";
import { test } from "node:test";

const repo = process.env.GROKMAP_TEST_REPO;
const file = process.env.GROKMAP_TEST_FILE;

test("paints the gutter from grokmap lines, and follows unsaved edits", { skip: !repo || !file }, async () => {
  const fsPath = path.join(repo!, file!);
  let text = fs.readFileSync(fsPath, "utf8");
  const painted = new Map<string, { start: number; end: number; hover: string }[]>();
  const infos: string[] = [];

  class Disposable {
    dispose(): void {}
  }
  const uri = { scheme: "file", fsPath, toString: () => `file://${fsPath}` };
  const doc = {
    uri,
    get lineCount() {
      return text.split("\n").length;
    },
    getText: () => text,
    isDirty: false,
  };
  let nextType = 0;
  const editor = {
    document: doc,
    setDecorations(type: { key: string }, ranges: { range: { start: { line: number }; end: { line: number } }; hoverMessage: { value: string } }[]) {
      painted.set(type.key, ranges.map((r) => ({ start: r.range.start.line, end: r.range.end.line, hover: r.hoverMessage.value })));
    },
  };
  const listeners: Record<string, ((e: unknown) => void)[]> = {};
  const on = (name: string) => (fn: (e: unknown) => void) => {
    (listeners[name] ??= []).push(fn);
    return new Disposable();
  };
  const settings: Record<string, unknown> = { command: process.env.GROKMAP_COMMAND ?? "grokmap" };
  const vscode = {
    StatusBarAlignment: { Right: 2 },
    OverviewRulerLane: { Left: 1 },
    ViewColumn: { Beside: -2 },
    ConfigurationTarget: { Global: 1 },
    Uri: { joinPath: (_b: unknown, ...p: string[]) => ({ fsPath: p.join("/") }), parse: (s: string) => ({ ...uri, s }) },
    Range: class {
      start: { line: number };
      end: { line: number };
      constructor(a: number, _b: number, c: number, _d: number) {
        this.start = { line: a };
        this.end = { line: c };
      }
    },
    MarkdownString: class {
      isTrusted: unknown;
      constructor(public value: string) {}
    },
    window: {
      createOutputChannel: () => ({ appendLine: (l: string) => infos.push(l), dispose() {} }),
      createStatusBarItem: () => ({ show() {}, hide() {}, dispose() {}, text: "", tooltip: "" }),
      createTextEditorDecorationType: () => ({ key: `t${nextType++}`, dispose() {} }),
      visibleTextEditors: [editor],
      activeTextEditor: editor,
      onDidChangeVisibleTextEditors: on("visible"),
      onDidChangeActiveTextEditor: on("active"),
      setStatusBarMessage: () => new Disposable(),
      showWarningMessage: async (m: string) => (infos.push(m), undefined),
      showInformationMessage: async (m: string) => (infos.push(m), undefined),
      showErrorMessage: async (m: string) => (infos.push(m), undefined),
    },
    workspace: {
      getConfiguration: () => ({ get: (k: string, d: unknown) => (k in settings ? settings[k] : d), update: async () => {} }),
      onDidSaveTextDocument: on("save"),
      onDidChangeTextDocument: on("change"),
      onDidCloseTextDocument: on("close"),
      onDidChangeConfiguration: on("config"),
      createFileSystemWatcher: () => ({ onDidChange: on("w"), onDidCreate: on("w"), dispose() {} }),
      textDocuments: [doc],
    },
    commands: { registerCommand: () => new Disposable(), executeCommand: async () => {} },
    env: { clipboard: { writeText: async () => {} } },
  };
  // let `require("vscode")` inside the extension resolve to the stand-in
  const M = Module as unknown as { _load: (req: string, ...rest: unknown[]) => unknown };
  const realLoad = M._load;
  M._load = (req: string, ...rest: unknown[]) => (req === "vscode" ? vscode : realLoad(req, ...rest));
  const ext = await import("../src/extension");
  ext.activate({ subscriptions: [], extensionUri: {} } as never);

  const waitForPaint = async () => {
    for (let i = 0; i < 200 && painted.size === 0; i++) await new Promise((r) => setTimeout(r, 50));
  };
  await waitForPaint();
  const all = [...painted.values()].flat();
  assert.ok(all.length > 0, `nothing painted; log: ${infos.join(" | ")}`);
  assert.ok(all.some((s) => /Nobody has checked this|Understood/.test(s.hover)));
  const firstStart = Math.min(...all.map((s) => s.start));

  // insert two lines at the top of the unsaved buffer: every block moves down by two
  painted.clear();
  text = "# new line one\n# new line two\n" + text;
  for (const fn of listeners.change ?? []) fn({ document: doc, contentChanges: [{}] });
  await new Promise((r) => setTimeout(r, 900));
  await waitForPaint();
  const moved = [...painted.values()].flat();
  assert.equal(Math.min(...moved.map((s) => s.start)), firstStart + 2);
  ext.deactivate();
});
