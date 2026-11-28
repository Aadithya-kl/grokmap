import { execFile } from "node:child_process";
import * as path from "node:path";
import * as vscode from "vscode";
import {
  DECORATED,
  FileData,
  LABELS,
  Span,
  State,
  hoverMarkdown,
  statusText,
  statusTooltip,
  toSpans,
} from "./model";

const COLORS: Record<string, { gutter: string; ruler: string; tint: string }> = {
  unread: { gutter: "unread.svg", ruler: "#e5534b", tint: "rgba(229, 83, 75, 0.07)" },
  skimmed: { gutter: "skimmed.svg", ruler: "#ec8a54", tint: "rgba(236, 138, 84, 0.06)" },
  fading: { gutter: "fading.svg", ruler: "#e0b324", tint: "rgba(224, 179, 36, 0.06)" },
  understood: { gutter: "understood.svg", ruler: "#3fb950", tint: "rgba(63, 185, 80, 0.05)" },
};

let decorationTypes = new Map<string, vscode.TextEditorDecorationType>();
let status: vscode.StatusBarItem;
let output: vscode.OutputChannel;
const cache = new Map<string, FileData>(); // uri -> last result
const timers = new Map<string, NodeJS.Timeout>();
let enabled = true;
let warnedMissing = false;

export function activate(context: vscode.ExtensionContext): void {
  output = vscode.window.createOutputChannel("Grok-map");
  status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 90);
  status.command = "grokmap.who";
  enabled = config().get<boolean>("enabled", true);
  buildDecorationTypes(context);

  context.subscriptions.push(
    output,
    status,
    vscode.commands.registerCommand("grokmap.toggle", () => {
      enabled = !enabled;
      vscode.window.setStatusBarMessage(`Grok-map colours ${enabled ? "on" : "off"}`, 2500);
      refreshVisible();
    }),
    vscode.commands.registerCommand("grokmap.refresh", () => refreshVisible(true)),
    vscode.commands.registerCommand("grokmap.quiz", (uri?: vscode.Uri) => quiz(uri)),
    vscode.commands.registerCommand("grokmap.who", () => who()),
    vscode.window.onDidChangeVisibleTextEditors(() => refreshVisible()),
    vscode.window.onDidChangeActiveTextEditor(() => updateStatus()),
    vscode.workspace.onDidSaveTextDocument((doc) => schedule(doc, 0)),
    vscode.workspace.onDidChangeTextDocument((e) => {
      if (e.contentChanges.length) schedule(e.document, 800);
    }),
    vscode.workspace.onDidCloseTextDocument((doc) => cache.delete(doc.uri.toString())),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("grokmap")) {
        enabled = config().get<boolean>("enabled", true);
        buildDecorationTypes(context);
        refreshVisible(true);
      }
    }),
  );
  // The ledger changes when someone records a quiz (from the MCP server, the CLI or a pull).
  const watcher = vscode.workspace.createFileSystemWatcher("**/.grokmap/ledger.jsonl");
  context.subscriptions.push(
    watcher,
    watcher.onDidChange(() => refreshVisible(true)),
    watcher.onDidCreate(() => refreshVisible(true)),
  );
  refreshVisible();
}

export function deactivate(): void {
  for (const t of timers.values()) clearTimeout(t);
  for (const d of decorationTypes.values()) d.dispose();
}

function config(): vscode.WorkspaceConfiguration {
  return vscode.workspace.getConfiguration("grokmap");
}

function buildDecorationTypes(context: vscode.ExtensionContext): void {
  for (const d of decorationTypes.values()) d.dispose();
  decorationTypes = new Map();
  const tint = config().get<boolean>("tintLines", false);
  for (const state of DECORATED) {
    const c = COLORS[state];
    decorationTypes.set(
      state,
      vscode.window.createTextEditorDecorationType({
        gutterIconPath: vscode.Uri.joinPath(context.extensionUri, "media", c.gutter),
        gutterIconSize: "contain",
        overviewRulerColor: c.ruler,
        overviewRulerLane: vscode.OverviewRulerLane.Left,
        isWholeLine: true,
        backgroundColor: tint ? c.tint : undefined,
      }),
    );
  }
}

function schedule(doc: vscode.TextDocument, delay: number): void {
  if (doc.uri.scheme !== "file") return;
  const key = doc.uri.toString();
  clearTimeout(timers.get(key));
  timers.set(
    key,
    setTimeout(() => {
      timers.delete(key);
      void analyze(doc);
    }, delay),
  );
}

function refreshVisible(force = false): void {
  for (const editor of vscode.window.visibleTextEditors) {
    const key = editor.document.uri.toString();
    if (!force && cache.has(key)) paint(editor, cache.get(key)!);
    else schedule(editor.document, 0);
  }
  updateStatus();
}

function run(args: string[], cwd: string, stdin?: string): Promise<string> {
  const command = config().get<string>("command", "grokmap").trim() || "grokmap";
  const [exe, ...pre] = command.split(/\s+/);
  return new Promise((resolve, reject) => {
    const child = execFile(
      exe,
      [...pre, ...args],
      { cwd, maxBuffer: 32 * 1024 * 1024, timeout: 60_000, windowsHide: true },
      (err, stdout, stderr) => {
        if (err) {
          (err as Error & { stderr?: string }).stderr = stderr;
          reject(err);
        } else resolve(stdout);
      },
    );
    if (stdin !== undefined) child.stdin?.end(stdin);
  });
}

async function analyze(doc: vscode.TextDocument): Promise<void> {
  const file = doc.uri.fsPath;
  const cwd = path.dirname(file);
  try {
    const out = await run(["lines", file, "--json", "--stdin"], cwd, doc.getText());
    const data = JSON.parse(out) as FileData;
    cache.set(doc.uri.toString(), data);
  } catch (err) {
    const e = err as NodeJS.ErrnoException & { stderr?: string };
    cache.delete(doc.uri.toString());
    if (e.code === "ENOENT") warnMissing();
    else if (!/not inside a git repository|not a git repository/.test(e.stderr ?? "")) {
      output.appendLine(`grokmap lines ${file}: ${e.stderr || e.message}`);
    }
  }
  for (const editor of vscode.window.visibleTextEditors) {
    if (editor.document === doc) paint(editor, cache.get(doc.uri.toString()));
  }
  updateStatus();
}

function warnMissing(): void {
  if (warnedMissing) return;
  warnedMissing = true;
  void vscode.window
    .showWarningMessage(
      'grokmap needs its command-line tool. Install it with "pip install grokmap" (or set grokmap.command, e.g. to "uvx grokmap").',
      "Use uvx",
      "Open settings",
    )
    .then((choice) => {
      if (choice === "Use uvx") {
        void config().update("command", "uvx grokmap", vscode.ConfigurationTarget.Global);
        warnedMissing = false;
      } else if (choice === "Open settings") {
        void vscode.commands.executeCommand("workbench.action.openSettings", "grokmap.command");
      }
    });
}

function paint(editor: vscode.TextEditor, data: FileData | undefined): void {
  const byState = new Map<State, vscode.DecorationOptions[]>();
  if (enabled && data?.tracked) {
    const quizUri = `command:grokmap.quiz?${encodeURIComponent(JSON.stringify([editor.document.uri.toString()]))}`;
    const lastLine = editor.document.lineCount - 1;
    for (const span of toSpans(data.lines)) {
      if (!DECORATED.includes(span.state)) continue;
      const start = Math.min(span.start - 1, lastLine);
      const end = Math.min(span.end - 1, lastLine);
      const hover = new vscode.MarkdownString(hoverMarkdown(span, data.commits ?? {}, quizUri));
      hover.isTrusted = { enabledCommands: ["grokmap.quiz"] };
      const list = byState.get(span.state) ?? [];
      list.push({ range: new vscode.Range(start, 0, end, 0), hoverMessage: hover });
      byState.set(span.state, list);
    }
  }
  for (const [state, type] of decorationTypes) editor.setDecorations(type, byState.get(state as State) ?? []);
}

function updateStatus(): void {
  const editor = vscode.window.activeTextEditor;
  const data = editor ? cache.get(editor.document.uri.toString()) : undefined;
  const text = data ? statusText(data) : undefined;
  if (!text || !config().get<boolean>("statusBar", true)) {
    status.hide();
    return;
  }
  const debt = data!.summary!.debt_pct;
  status.text = `$(${debt >= 35 ? "warning" : "pass"}) ${text}`;
  status.tooltip = statusTooltip(data!);
  status.show();
}

async function quiz(arg?: vscode.Uri | string): Promise<void> {
  const uri = typeof arg === "string" ? vscode.Uri.parse(arg) : arg ?? vscode.window.activeTextEditor?.document.uri;
  if (!uri || uri.scheme !== "file") {
    void vscode.window.showInformationMessage("Open a file in a git repository to get a Grok-map quiz.");
    return;
  }
  const doc = vscode.workspace.textDocuments.find((d) => d.uri.toString() === uri.toString());
  if (doc?.isDirty) await doc.save();
  try {
    const cwd = path.dirname(uri.fsPath);
    // quiz takes repository-relative paths; `lines` tells us this file's
    const info = cache.get(uri.toString()) ?? (JSON.parse(await run(["lines", uri.fsPath, "--json"], cwd)) as FileData);
    if (!info.tracked) {
      void vscode.window.showInformationMessage(`Grok-map: ${info.note ?? "this file is not tracked."}`);
      return;
    }
    const brief = await run(["quiz", info.path], cwd);
    await vscode.env.clipboard.writeText(brief);
    const shown = await vscode.workspace.openTextDocument({ language: "markdown", content: brief });
    await vscode.window.showTextDocument(shown, { viewColumn: vscode.ViewColumn.Beside, preview: true });
    void vscode.window.showInformationMessage(
      "Quiz brief copied. Paste it into your coding agent's chat (Copilot Chat, Claude Code, Cursor): it asks you the questions and records your result.",
    );
  } catch (err) {
    const e = err as NodeJS.ErrnoException & { stderr?: string };
    if (e.code === "ENOENT") warnMissing();
    else void vscode.window.showErrorMessage(`Grok-map quiz failed: ${e.stderr || e.message}`);
  }
}

async function who(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  const data = editor ? cache.get(editor.document.uri.toString()) : undefined;
  if (!editor || !data?.summary) {
    void vscode.window.showInformationMessage("Grok-map has no data for this file yet.");
    return;
  }
  const s = data.summary;
  const items: vscode.QuickPickItem[] = [
    { label: `$(graph) Comprehension debt ${s.debt_pct}%`, description: data.critical ? "critical path" : undefined },
    ...DECORATED.map((st) => ({ label: LABELS[st], description: `${s[st as keyof typeof s]} lines` })),
    ...Object.entries(s.people).map(([p, n]) => ({ label: `$(person) ${p}`, description: `understands ${n} lines` })),
    { label: "$(mortar-board) Quiz me on this file", description: "grokmap.quiz" },
  ];
  const pick = await vscode.window.showQuickPick(items, { title: `Grok-map · ${data.path}` });
  if (pick?.description === "grokmap.quiz") void quiz(editor.document.uri);
}
