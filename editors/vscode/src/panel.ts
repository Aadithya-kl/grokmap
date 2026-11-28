import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import { config, errorText, isMissing, run } from "./cli";
import type { FileData } from "./model";
import {
  Assistant,
  Dashboard,
  Grade,
  Question,
  QuizJson,
  QuizTarget,
  availableAssistants,
  averageScore,
  dashboard,
  gradePrompt,
  handoffPrompt,
  markArgs,
  parseJsonReply,
  questionCount,
  questionPrompt,
  rangesText,
  readGrades,
  readQuestions,
  totalLines,
  verdict,
} from "./panelModel";

const REPO_KEY = "grokmap.repo";
const RECENT_KEY = "grokmap.recentRepos";
const PASS_SCORE = 0.7;

type Phase = "norepo" | "loading" | "nocli" | "error" | "ready";

interface QuizState {
  scope: string; // file path, or "" for the whole repository
  title: string;
  phase: "loading" | "nothing" | "choose" | "asking" | "grading" | "done" | "error";
  message?: string;
  lines?: number;
  span?: string;
  questions?: Question[];
  answers?: string[];
  grades?: Grade[];
  score?: number;
  verdict?: string;
  saved?: string;
  model?: string;
  models?: { id: string; name: string }[];
}

interface ActiveFile {
  path: string;
  name: string;
  tracked: boolean;
  critical?: boolean;
  note?: string;
  summary?: FileData["summary"];
}

export interface ViewState {
  phase: Phase;
  repo?: { path: string; name: string };
  recent: { path: string; name: string }[];
  workspace: { path: string; name: string }[];
  dash?: Dashboard;
  active?: ActiveFile;
  quiz?: QuizState;
  assistants: { id: string; name: string }[];
  error?: string;
  command: string;
  updated?: string;
}

/** The Grok-map panel: a sidebar view, and the same page in an editor tab on request. */
export class GrokmapPanel implements vscode.WebviewViewProvider {
  static readonly viewId = "grokmap.panel";
  private views = new Set<vscode.Webview>();
  private tab?: vscode.WebviewPanel;
  private state: ViewState;
  private targets: QuizTarget[] = [];
  private cancel?: vscode.CancellationTokenSource;
  private loading?: Promise<void>;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly fileData: (uri: vscode.Uri) => Promise<FileData | undefined>,
  ) {
    this.state = { phase: "loading", recent: [], workspace: [], assistants: [], command: this.command() };
  }

  // ------------------------------------------------------------ webview plumbing

  resolveWebviewView(view: vscode.WebviewView): void {
    this.attach(view.webview);
    view.onDidDispose(() => this.views.delete(view.webview));
    view.onDidChangeVisibility(() => {
      if (view.visible) this.post();
    });
  }

  openInEditor(): void {
    if (this.tab) {
      this.tab.reveal();
      return;
    }
    this.tab = vscode.window.createWebviewPanel("grokmap.tab", "Grok-map", vscode.ViewColumn.Active, {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "media")],
    });
    this.tab.iconPath = vscode.Uri.joinPath(this.context.extensionUri, "media", "icon.png");
    this.attach(this.tab.webview);
    this.tab.onDidDispose(() => {
      if (this.tab) this.views.delete(this.tab.webview);
      this.tab = undefined;
    });
  }

  private attach(webview: vscode.Webview): void {
    webview.options = { enableScripts: true, localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "media")] };
    webview.html = this.html(webview);
    webview.onDidReceiveMessage((m) => void this.onMessage(m));
    this.views.add(webview);
    if (!this.loading && this.state.phase === "loading") void this.load();
  }

  private html(webview: vscode.Webview): string {
    const media = (f: string) => webview.asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri, "media", f)).toString();
    const nonce = Array.from({ length: 24 }, () => Math.floor(Math.random() * 36).toString(36)).join("");
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${webview.cspSource} data:; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="${media("panel.css")}">
<title>Grok-map</title>
</head>
<body>
<div id="app" data-logo="${media("logo.svg")}"></div>
<script nonce="${nonce}" src="${media("panel.js")}"></script>
</body>
</html>`;
  }

  private post(): void {
    this.state.command = this.command();
    for (const w of this.views) void w.postMessage({ type: "state", state: this.state });
  }

  private set(patch: Partial<ViewState>): void {
    this.state = { ...this.state, ...patch };
    this.post();
  }

  private setQuiz(patch: Partial<QuizState>): void {
    if (!this.state.quiz) return;
    this.state.quiz = { ...this.state.quiz, ...patch };
    this.post();
  }

  private command(): string {
    return config().get<string>("command", "grokmap").trim() || "grokmap";
  }

  // ------------------------------------------------------------ repository

  private workspaceRepos(): { path: string; name: string }[] {
    return (vscode.workspace.workspaceFolders ?? [])
      .filter((f) => f.uri.scheme === "file")
      .map((f) => ({ path: f.uri.fsPath, name: f.name }));
  }

  private recent(): { path: string; name: string }[] {
    const list = this.context.globalState.get<string[]>(RECENT_KEY, []);
    return list.filter((p) => fs.existsSync(p)).map((p) => ({ path: p, name: path.basename(p) }));
  }

  private currentRepo(): string | undefined {
    const ws = this.workspaceRepos();
    const savedPath = this.context.globalState.get<string>(REPO_KEY);
    const saved = savedPath && fs.existsSync(savedPath) ? savedPath : undefined;
    // With a folder open, use it (or the repository picked inside it). With none, the last pick.
    if (ws.length) {
      const inside = saved && ws.some((w) => saved === w.path || saved.startsWith(w.path + path.sep));
      return inside ? saved : ws[0].path;
    }
    return saved;
  }

  async useRepo(folder: string): Promise<void> {
    const recent = [folder, ...this.context.globalState.get<string[]>(RECENT_KEY, []).filter((p) => p !== folder)].slice(0, 6);
    await this.context.globalState.update(REPO_KEY, folder);
    await this.context.globalState.update(RECENT_KEY, recent);
    this.state.quiz = undefined;
    this.state.repo = { path: folder, name: path.basename(folder) };
    await this.load();
  }

  async chooseRepo(): Promise<void> {
    const picked = await vscode.window.showOpenDialog({
      canSelectFolders: true,
      canSelectFiles: false,
      canSelectMany: false,
      openLabel: "Use this repository",
      title: "Grok-map: choose a git repository",
    });
    if (picked?.[0]) await this.useRepo(picked[0].fsPath);
  }

  async load(): Promise<void> {
    const task = this.doLoad();
    this.loading = task;
    try {
      await task;
    } finally {
      if (this.loading === task) this.loading = undefined;
    }
  }

  private async doLoad(): Promise<void> {
    const repoPath = this.state.repo?.path ?? this.currentRepo();
    const base = {
      recent: this.recent(),
      workspace: this.workspaceRepos(),
      assistants: this.assistants().map((a) => ({ id: a.id, name: a.name })),
    };
    if (!repoPath) {
      this.set({ ...base, phase: "norepo", repo: undefined, dash: undefined, active: undefined });
      return;
    }
    const repo = { path: repoPath, name: path.basename(repoPath) };
    this.set({ ...base, phase: this.state.dash && this.state.repo?.path === repoPath ? "ready" : "loading", repo });
    try {
      const out = await run(["status", "--json"], repoPath, undefined, 180_000);
      const dash = dashboard(JSON.parse(out));
      this.set({ phase: "ready", dash, error: undefined, updated: new Date().toISOString() });
      await this.followEditor();
    } catch (err) {
      if (isMissing(err)) this.set({ phase: "nocli", error: undefined });
      else {
        const text = errorText(err);
        const notGit = /not a git repository|not inside a git repository/i.test(text);
        this.set({
          phase: "error",
          error: notGit ? `${repo.name} isn't a git repository. Choose the folder that contains .git.` : text.split("\n").slice(-3).join("\n"),
        });
      }
    }
  }

  /** Show the file in the active editor when it belongs to the chosen repository. */
  async followEditor(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    const repo = this.state.repo?.path;
    if (!editor || !repo || editor.document.uri.scheme !== "file") return;
    const file = editor.document.uri.fsPath;
    const rel = path.relative(repo, file);
    if (rel.startsWith("..") || path.isAbsolute(rel)) return;
    const data = await this.fileData(editor.document.uri);
    if (!data) return;
    this.set({
      active: {
        path: data.path,
        name: path.basename(data.path),
        tracked: data.tracked,
        critical: data.critical,
        note: data.note,
        summary: data.summary,
      },
    });
  }

  // ------------------------------------------------------------ messages

  private async onMessage(m: { type: string; [k: string]: unknown }): Promise<void> {
    switch (m.type) {
      case "ready":
        this.post();
        if (this.state.phase === "loading" && !this.loading) await this.load();
        break;
      case "chooseRepo":
        await this.chooseRepo();
        break;
      case "useRepo":
        await this.useRepo(String(m.path));
        break;
      case "refresh":
        await this.load();
        break;
      case "openFile":
        await this.openFile(String(m.path));
        break;
      case "quiz":
        await this.startQuiz(String(m.path ?? ""));
        break;
      case "answers":
        await this.grade((m.answers as string[]) ?? []);
        break;
      case "pickModel":
        await this.context.globalState.update("grokmap.model", String(m.id));
        if (this.state.quiz) await this.startQuiz(this.state.quiz.scope);
        break;
      case "handoff":
        await this.handoff(String(m.id));
        break;
      case "closeQuiz":
        this.cancel?.cancel();
        this.set({ quiz: undefined });
        break;
      case "useUvx":
        await config().update("command", "uvx grokmap", vscode.ConfigurationTarget.Global);
        await this.load();
        break;
      case "copy":
        await vscode.env.clipboard.writeText(String(m.text));
        vscode.window.setStatusBarMessage("Copied", 2000);
        break;
      case "settings":
        await vscode.commands.executeCommand("workbench.action.openSettings", "grokmap");
        break;
      case "openInEditor":
        this.openInEditor();
        break;
      case "link":
        await vscode.env.openExternal(vscode.Uri.parse(String(m.url)));
        break;
    }
  }

  private async openFile(rel: string): Promise<void> {
    const repo = this.state.repo?.path;
    if (!repo) return;
    const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(path.join(repo, rel)));
    await vscode.window.showTextDocument(doc, { preview: true, viewColumn: this.tab ? vscode.ViewColumn.Beside : undefined });
  }

  // ------------------------------------------------------------ quiz

  /** Quiz on a file opened in the editor; switches the panel to that file's repository if needed. */
  async quizFile(uri: vscode.Uri, rel: string): Promise<void> {
    const file = uri.fsPath;
    const relNative = rel.split("/").join(path.sep);
    const root = file.endsWith(relNative) ? file.slice(0, file.length - relNative.length).replace(/[\\/]+$/, "") : undefined;
    if (root && path.resolve(root) !== path.resolve(this.state.repo?.path ?? "")) await this.useRepo(root);
    await this.startQuiz(rel);
  }

  /** Start a quiz on a file (repository-relative path), or on the whole repository with "". */
  async startQuiz(scope: string): Promise<void> {
    const repo = this.state.repo?.path;
    if (!repo) {
      await this.load();
      if (!this.state.repo) return;
    }
    this.cancel?.cancel();
    this.targets = [];
    const title = scope ? path.basename(scope) : "Code nobody has checked";
    this.set({ quiz: { scope, title, phase: "loading", message: "Finding the code to quiz you on…" } });
    try {
      const args = ["quiz", ...(scope ? [scope] : []), "--format", "json", "--max-lines", "160"];
      const q = JSON.parse(await run(args, this.state.repo!.path)) as QuizJson;
      this.targets = q.targets;
      if (!q.targets.length) {
        this.setQuiz({ phase: "nothing", message: undefined });
        return;
      }
      const span = q.targets.length === 1 ? `lines ${rangesText(q.targets[0].ranges)}` : `${q.targets.length} files`;
      this.setQuiz({ lines: totalLines(q.targets), span, title: q.targets.length === 1 ? path.basename(q.targets[0].path) : title });

      const models = await this.models();
      if (!models.length) {
        this.setQuiz({ phase: "choose", message: undefined });
        return;
      }
      const preferred = this.context.globalState.get<string>("grokmap.model");
      const model = models.find((x) => x.id === preferred) ?? models[0];
      this.setQuiz({
        model: model.name,
        models: models.map((x) => ({ id: x.id, name: x.name })),
        message: "Reading the code and writing your questions…",
      });
      const n = questionCount(q.targets);
      const reply = await this.ask(model, questionPrompt(q.targets, n));
      const questions = readQuestions(parseJsonReply(reply), n);
      this.setQuiz({ phase: "asking", questions, answers: questions.map(() => ""), message: undefined });
    } catch (err) {
      if (err instanceof vscode.CancellationError) return;
      if (isMissing(err)) {
        this.set({ phase: "nocli", quiz: undefined });
        return;
      }
      this.quizFailed(err);
    }
  }

  private quizFailed(err: unknown): void {
    const text = errorText(err);
    const lm = err instanceof vscode.LanguageModelError;
    this.setQuiz({
      phase: lm ? "choose" : "error",
      message: lm
        ? `VS Code's AI couldn't run the quiz (${text}). You can run it with your assistant instead.`
        : `Something went wrong: ${text}`,
    });
  }

  private async grade(answers: string[]): Promise<void> {
    const quiz = this.state.quiz;
    if (!quiz?.questions || !this.targets.length) return;
    this.setQuiz({ phase: "grading", answers, message: "Grading your answers…" });
    try {
      const models = await this.models();
      const model = models.find((x) => x.name === quiz.model) ?? models[0];
      if (!model) {
        this.setQuiz({ phase: "choose" });
        return;
      }
      const reply = await this.ask(model, gradePrompt(this.targets, quiz.questions, answers));
      const grades = readGrades(parseJsonReply(reply), quiz.questions.length);
      const score = averageScore(grades);
      const v = verdict(score, PASS_SCORE);
      this.setQuiz({ phase: "done", grades, score, verdict: v, message: undefined });
      // the ledger counts any record below the pass score as skimmed, so a zero isn't recorded
      if (score > 0) await this.record(score, model.name);
      else this.setQuiz({ saved: "Nothing was recorded, so this code still counts as unchecked." });
    } catch (err) {
      if (err instanceof vscode.CancellationError) return;
      this.quizFailed(err);
    }
  }

  private async record(score: number, modelName: string): Promise<void> {
    const repo = this.state.repo?.path;
    if (!repo) return;
    try {
      await run(markArgs(this.targets, score, `quiz in the VS Code panel, graded by ${modelName}`), repo);
      const lines = totalLines(this.targets);
      this.setQuiz({ saved: `Saved to .grokmap/ledger.jsonl for ${lines} line${lines === 1 ? "" : "s"}. Commit it so your team sees it.` });
      await vscode.commands.executeCommand("grokmap.refresh");
      await this.load();
    } catch (err) {
      this.setQuiz({ saved: `Couldn't save the result: ${errorText(err)}` });
    }
  }

  private async models(): Promise<vscode.LanguageModelChat[]> {
    if (!vscode.lm?.selectChatModels) return [];
    try {
      const all = await vscode.lm.selectChatModels();
      // prefer capable general models; keep the user's order otherwise
      return all.filter((m) => !/embedding|mini-?fast/i.test(m.id));
    } catch {
      return [];
    }
  }

  private async ask(model: vscode.LanguageModelChat, prompt: string): Promise<string> {
    this.cancel?.dispose();
    this.cancel = new vscode.CancellationTokenSource();
    const res = await model.sendRequest(
      [vscode.LanguageModelChatMessage.User(prompt)],
      { justification: "Grok-map writes and grades a short quiz on the code you picked." },
      this.cancel.token,
    );
    let text = "";
    for await (const part of res.text) text += part;
    return text;
  }

  // ------------------------------------------------------------ hand-off

  private assistants(): Assistant[] {
    return availableAssistants((id) => !!vscode.extensions.getExtension(id), vscode.env.appName);
  }

  private async handoff(id: string): Promise<void> {
    const quiz = this.state.quiz;
    const repo = this.state.repo?.path;
    if (!quiz || !repo) return;
    let brief: string;
    try {
      brief = await run(["quiz", ...(quiz.scope ? [quiz.scope] : []), "--max-lines", "160"], repo);
    } catch (err) {
      this.setQuiz({ phase: "error", message: errorText(err) });
      return;
    }
    const prompt = handoffPrompt(brief);
    await vscode.env.clipboard.writeText(prompt);
    const target = this.assistants().find((a) => a.id === id);
    let opened = false;
    for (const c of target?.commands ?? []) {
      try {
        if (c.chat) await vscode.commands.executeCommand(c.command, { query: prompt, isPartialQuery: true });
        else await vscode.commands.executeCommand(c.command);
        opened = true;
        break;
      } catch {
        // try the next one
      }
    }
    const paste = process.platform === "darwin" ? "⌘V" : "Ctrl+V";
    if (target && opened) {
      const filled = target.commands.some((c) => c.chat);
      void vscode.window.showInformationMessage(
        filled
          ? `Grok-map: the quiz is in ${target.name}. Send it to start.`
          : `Grok-map: quiz prompt copied. Paste it into ${target.name} with ${paste} and send.`,
      );
    } else {
      void vscode.window.showInformationMessage(`Grok-map: quiz prompt copied. Paste it into your AI assistant's chat with ${paste}.`);
    }
  }
}
