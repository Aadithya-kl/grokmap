import { execFile } from "node:child_process";
import * as vscode from "vscode";

export function config(): vscode.WorkspaceConfiguration {
  return vscode.workspace.getConfiguration("grokmap");
}

export type RunError = NodeJS.ErrnoException & { stderr?: string };

/** Run the grokmap CLI (or whatever grokmap.command says) and return its stdout. */
export function run(args: string[], cwd: string, stdin?: string, timeout = 60_000): Promise<string> {
  const command = config().get<string>("command", "grokmap").trim() || "grokmap";
  const [exe, ...pre] = command.split(/\s+/);
  return new Promise((resolve, reject) => {
    const child = execFile(
      exe,
      [...pre, ...args],
      { cwd, maxBuffer: 64 * 1024 * 1024, timeout, windowsHide: true },
      (err, stdout, stderr) => {
        if (err) {
          (err as RunError).stderr = stderr;
          reject(err);
        } else resolve(stdout);
      },
    );
    if (stdin !== undefined) child.stdin?.end(stdin);
  });
}

export function isMissing(err: unknown): boolean {
  return (err as RunError)?.code === "ENOENT";
}

export function errorText(err: unknown): string {
  const e = err as RunError;
  return (e?.stderr || e?.message || String(err)).trim();
}
