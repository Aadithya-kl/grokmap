// Grok-map panel front end. Renders the state the extension posts; sends user actions back.
(function () {
  "use strict";
  const vscode = typeof acquireVsCodeApi === "function" ? acquireVsCodeApi() : { postMessage() {}, getState() {}, setState() {} };
  const app = document.getElementById("app");
  const LOGO = app.dataset.logo;
  let state = null;
  // local quiz progress, kept across re-renders and webview reloads
  let local = Object.assign({ key: "", index: 0, drafts: [] }, vscode.getState() || {});

  const send = (type, data) => vscode.postMessage(Object.assign({ type }, data || {}));
  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  // escape, then show `code` spans the way the model writes them
  const rich = (s) => esc(s).replace(/`([^`\n]+)`/g, "<code>$1</code>");
  const fmt = (n) => Number(n || 0).toLocaleString("en-US");
  const pct = (n) => `${Math.round(Number(n || 0))}%`;
  const plural = (n, w) => `${fmt(n)} ${w}${n === 1 ? "" : "s"}`;

  const ICON = {
    refresh: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9"/><path d="M13.5 2.5v3h-3"/></svg>',
    expand: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 2.5h4v4M13.5 2.5 8.5 7.5M6.5 13.5h-4v-4M2.5 13.5l5-5"/></svg>',
    repo: '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><path d="M3 2.5h8.5a1 1 0 0 1 1 1v10H4.5A1.5 1.5 0 0 1 3 12V2.5Z"/><path d="M3 12a1.5 1.5 0 0 1 1.5-1.5h8"/></svg>',
    back: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M10 3 5 8l5 5"/></svg>',
    quiz: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2 1.5 5.2 8 8.4l6.5-3.2L8 2Z"/><path d="M4 6.6v3.2c0 1 1.8 2.2 4 2.2s4-1.2 4-2.2V6.6"/></svg>',
    open: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><path d="M4 1.5h5.5L13 5v9.5H4z"/><path d="M9.5 1.5V5H13"/></svg>',
    check: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m3 8.5 3.2 3L13 4.5"/></svg>',
    copy: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="5" y="5" width="8.5" height="8.5" rx="1.5"/><path d="M11 5V3.5A1.5 1.5 0 0 0 9.5 2h-6A1.5 1.5 0 0 0 2 3.5v6A1.5 1.5 0 0 0 3.5 11H5"/></svg>',
    folder: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><path d="M1.5 4a1 1 0 0 1 1-1h3.6l1.5 1.6h5.9a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1V4Z"/></svg>',
  };

  // ------------------------------------------------------------ pieces

  function ring(value, size, caption, label) {
    const r = 42;
    const c = 2 * Math.PI * r;
    const v = Math.max(0, Math.min(100, Number(value) || 0));
    return `<div class="ring" style="width:${size}px;height:${size}px" role="img" aria-label="${esc(label)}">
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <defs><linearGradient id="mintGrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="var(--mint-hi)"/><stop offset="1" stop-color="var(--mint)"/></linearGradient></defs>
        <circle class="track" cx="50" cy="50" r="${r}" fill="none" stroke-width="8"/>
        <circle class="value" cx="50" cy="50" r="${r}" fill="none" stroke-width="8" stroke-linecap="round"
          stroke-dasharray="${c.toFixed(2)}" stroke-dashoffset="${(c * (1 - v / 100)).toFixed(2)}"/>
      </svg>
      <div class="center"><div class="big">${pct(v)}</div><div class="cap">${esc(caption)}</div></div>
    </div>`;
  }

  function stateBar(s, thin) {
    const total = (s.understood || 0) + (s.fading || 0) + (s.skimmed || 0) + (s.unread || 0);
    if (!total) return `<div class="bar${thin ? " thin" : ""}"></div>`;
    const seg = (k) => (s[k] ? `<i class="s-${k}" style="flex:${s[k]}" title="${esc(LABEL[k])}: ${fmt(s[k])} lines"></i>` : "");
    return `<div class="bar${thin ? " thin" : ""}" aria-hidden="true">${seg("understood")}${seg("fading")}${seg("skimmed")}${seg("unread")}</div>`;
  }
  const LABEL = { understood: "Understood", fading: "Fading", skimmed: "Only skimmed", unread: "Unchecked" };

  function legend(s) {
    return `<div class="legend">${["unread", "skimmed", "fading", "understood"]
      .map((k) => `<div><span class="sw s-${k}"></span><span>${LABEL[k]}</span><span class="n">${fmt(s[k])}</span></div>`)
      .join("")}</div>`;
  }

  function debtPill(debt) {
    const cls = debt >= 35 ? "bad" : debt >= 15 ? "warn" : "good";
    const word = debt >= 35 ? "High debt" : debt >= 15 ? "Some debt" : "Low debt";
    return `<span class="pill ${cls}"><span class="dot"></span>${word} · ${pct(debt)}</span>`;
  }

  const PALETTE = ["#6e7bf2", "#c2358f", "#14919b", "#e07a3a", "#7c4dcc", "#3b6fe0", "#2e9d5b", "#b8860b"];
  function avatar(name) {
    let h = 0;
    for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    const base = name.split("@")[0].replace(/[._-]+/g, " ").trim();
    const parts = base.split(/\s+/);
    const initials = ((parts[0] || "?")[0] + (parts[1] ? parts[1][0] : (parts[0] || "")[1] || "")).toUpperCase();
    return `<span class="avatar" style="background:${PALETTE[h % PALETTE.length]}" aria-hidden="true">${esc(initials)}</span>`;
  }

  function header() {
    const repo = state && state.repo;
    return `<div class="top">
      <div class="brand"><img src="${esc(LOGO)}" alt=""><span class="word">Grok-map</span>
        ${repo ? `<button class="repo-chip" data-act="chooseRepo" title="${esc(repo.path)} · click to switch">${ICON.repo}<span>${esc(repo.name)}</span></button>` : ""}
      </div>
      ${repo ? `<button class="icon-btn" data-act="refresh" title="Refresh" aria-label="Refresh">${ICON.refresh}</button>` : ""}
      <button class="icon-btn" data-act="openInEditor" title="Open in an editor tab" aria-label="Open in an editor tab">${ICON.expand}</button>
    </div>`;
  }

  // ------------------------------------------------------------ screens

  function noRepo() {
    const recent = (state.recent || []).slice(0, 4);
    const ws = state.workspace || [];
    const options = [...ws.map((r) => ({ ...r, sub: "Open in this window" })), ...recent.filter((r) => !ws.some((w) => w.path === r.path)).map((r) => ({ ...r, sub: r.path }))];
    return `<div class="empty fade-in">
      <img class="logo" src="${esc(LOGO)}" alt="">
      <h2>Who understands your code?</h2>
      <p>Pick a git repository. Grok-map finds the AI-written code nobody on your team has checked, then quizzes you on it.</p>
      <button class="btn primary" data-act="chooseRepo">${ICON.folder} Choose a repository</button>
    </div>
    ${options.length ? `<div class="section-title">Recent</div>${options
      .map((r) => `<button class="list-btn" data-act="useRepo" data-path="${esc(r.path)}">${ICON.repo}<span class="grow"><div class="ellipsis">${esc(r.name)}</div><div class="sub ellipsis">${esc(r.sub)}</div></span></button>`)
      .join("")}` : ""}`;
  }

  function noCli() {
    return `<div class="card fade-in">
      <h3>One-time setup</h3>
      <p style="margin:0 0 4px">Grok-map reads your git history with a small command-line tool. Install it once:</p>
      <div class="code"><span>pip install grokmap</span><button class="icon-btn" data-act="copy" data-text="pip install grokmap" title="Copy">${ICON.copy}</button></div>
      <div class="row" style="margin-top:12px">
        <button class="btn primary grow" data-act="refresh">I've installed it</button>
        <button class="btn" data-act="useUvx" title="Runs it with uv, without installing">Use uvx instead</button>
      </div>
      <p class="note">Already installed somewhere else? Set the path in <a data-act="settings">Grok-map settings</a>. Now using <span class="mono">${esc(state.command)}</span>.</p>
    </div>`;
  }

  function errorView() {
    return `<div class="card error fade-in">
      <h3>Couldn't read this repository</h3>
      <pre>${esc(state.error || "Unknown error")}</pre>
      <div class="row" style="margin-top:12px">
        <button class="btn primary" data-act="chooseRepo">Choose another</button>
        <button class="btn" data-act="refresh">Try again</button>
      </div>
    </div>`;
  }

  function loading() {
    return `<div class="card hero"><div class="skel" style="width:92px;height:92px;border-radius:50%"></div>
      <div class="grow"><div class="skel" style="height:10px;width:40%"></div><div class="skel" style="height:16px;width:85%;margin-top:9px"></div><div class="skel" style="height:16px;width:55%;margin-top:7px"></div></div></div>
      <div class="card"><div class="skel" style="height:8px"></div><div class="skel" style="height:12px;width:70%;margin-top:14px"></div><div class="skel" style="height:12px;width:60%;margin-top:8px"></div></div>
      <p class="muted small" style="text-align:center">Reading the git history of ${esc(state.repo ? state.repo.name : "your repository")}…</p>`;
  }

  function dashboardView() {
    const d = state.dash;
    if (!d.ai) {
      return `<div class="card empty fade-in">
        <img class="logo" src="${esc(LOGO)}" alt="" style="width:48px;height:48px">
        <h2>No AI-written code found yet</h2>
        <p>Grok-map spots AI code by the trailers and authors coding agents leave in commits, such as <span class="mono">Co-Authored-By: Claude</span>. ${fmt(d.lines)} lines checked.</p>
        <button class="btn" data-act="link" data-url="https://github.com/Aadithya-kl/grokmap#how-it-tells-ai-code-from-human-code">How detection works</button>
      </div>${activeCard()}`;
    }
    const nobody = d.open;
    const hero = `<div class="card hero fade-in">
      ${ring(d.understoodPct, 92, "understood", `${pct(d.understoodPct)} of AI-written code understood`)}
      <div class="hero-text">
        <div class="kicker">Comprehension</div>
        <div class="headline">${nobody ? `<b>${fmt(nobody)}</b> AI-written ${nobody === 1 ? "line" : "lines"} nobody fully understands` : "Every AI-written line is understood"}</div>
        <div class="row" style="flex-wrap:wrap;gap:6px">${debtPill(d.debtPct)}<span class="muted small">${fmt(d.ai)} of ${fmt(d.lines)} lines by AI</span></div>
      </div>
    </div>`;
    const breakdown = `<div class="card fade-in">
      <h3>AI-written code<span class="aside">${pct(d.aiPct)} of the repository</span></h3>
      ${stateBar(d)}${legend(d)}
      <div class="cta">
        <button class="btn primary block" data-act="quiz" data-path="" ${nobody ? "" : "disabled"}>${ICON.quiz} Quiz me on code nobody checked</button>
        <div class="hint">About 2 minutes · 3 to 6 questions</div>
      </div>
    </div>`;
    const risky = d.risky.length
      ? `<div class="card fade-in"><h3>Needs attention<span class="aside">${plural(d.risky.length + d.riskyMore, "file")}</span></h3><div class="files">${d.risky
          .map(
            (f) => `<div class="file" tabindex="0" data-act="openFile" data-path="${esc(f.path)}" title="${esc(f.path)}">
              <div class="grow"><div class="name ellipsis">${esc(f.name)}</div><div class="dir ellipsis">${esc(f.dir || "/")}</div></div>
              <div class="count"><b>${fmt(f.open)}</b> / ${fmt(f.ai)}</div>
              <div class="actions"><button class="btn sm" data-act="quiz" data-path="${esc(f.path)}">${ICON.quiz} Quiz</button><button class="btn sm ghost" data-act="openFile" data-path="${esc(f.path)}" title="Open">${ICON.open}</button></div>
              ${stateBar(f, true)}
            </div>`,
          )
          .join("")}</div>${d.riskyMore ? `<div class="more">and ${plural(d.riskyMore, "more file")}</div>` : ""}</div>`
      : "";
    const people = `<div class="card fade-in"><h3>Who understands it</h3>${
      d.people.length
        ? `<div class="people">${d.people
            .slice(0, 6)
            .map((p) => `<div class="person">${avatar(p.name)}<span class="ellipsis">${esc(p.name)}</span><span class="n">${fmt(p.lines)} lines</span></div>`)
            .join("")}</div>`
        : `<p class="muted small" style="margin:0">Nobody yet. Take the first quiz and you'll show up here.</p>`
    }</div>`;
    const tools = d.tools.length
      ? `<div class="card fade-in"><h3>Written by</h3><div class="chips">${d.tools.map((t) => `<span class="chip">${esc(t.name)}<span class="n">${fmt(t.lines)}</span></span>`).join("")}</div></div>`
      : "";
    return `${hero}<div class="grid"><div>${breakdown}${activeCard()}</div><div>${risky}${people}${tools}</div></div>`;
  }

  function activeCard() {
    const a = state.active;
    if (!a) return "";
    const s = a.summary;
    if (!a.tracked || !s) {
      return `<div class="card active-file fade-in"><h3>This file</h3><div class="title ellipsis">${esc(a.name)}</div><div class="meta">${esc(a.note || "Not tracked by git yet.")}</div></div>`;
    }
    const open = (s.unread || 0) + (s.skimmed || 0) + (s.fading || 0);
    const people = Object.keys(s.people || {});
    return `<div class="card active-file fade-in">
      <h3>This file${a.critical ? '<span class="aside" style="color:var(--unread)">critical path</span>' : ""}</h3>
      <div class="title ellipsis" title="${esc(a.path)}">${esc(a.name)}</div>
      <div class="meta">${s.ai ? `${fmt(s.ai)} of ${fmt(s.lines)} lines by AI · debt ${pct(s.debt_pct)}${people.length ? ` · understood by ${esc(people.slice(0, 2).join(", "))}${people.length > 2 ? ` +${people.length - 2}` : ""}` : ""}` : `${fmt(s.lines)} lines, all written by people`}</div>
      ${s.ai ? stateBar(s) : ""}
      ${s.ai ? `<div class="row" style="margin-top:11px"><button class="btn ${open ? "primary" : ""} grow" data-act="quiz" data-path="${esc(a.path)}">${ICON.quiz} ${open ? "Quiz me on this file" : "Quiz me again"}</button></div>` : ""}
    </div>`;
  }

  // ------------------------------------------------------------ quiz screens

  function quizView() {
    const q = state.quiz;
    const head = `<div class="quiz-head">
      <button class="icon-btn" data-act="closeQuiz" title="Back to the overview" aria-label="Back">${ICON.back}</button>
      <div class="grow"><div class="t ellipsis">Quiz · ${esc(q.title)}</div><div class="s">${q.lines ? `${plural(q.lines, "line")}${q.span ? ` · ${esc(q.span)}` : ""}` : "&nbsp;"}</div></div>
    </div>`;
    let body = "";
    if (q.phase === "loading" || q.phase === "grading") {
      body = `<div class="card thinking fade-in"><div class="orb"></div><div><div style="font-weight:600">${esc(q.message || "Working…")}</div><div class="muted small">${q.model ? `Using ${esc(q.model)}` : "This takes a few seconds"}</div></div></div>
        ${q.phase === "loading" ? `<div class="card"><div class="skel" style="height:10px;width:30%"></div><div class="skel" style="height:15px;margin-top:12px"></div><div class="skel" style="height:15px;width:70%;margin-top:7px"></div><div class="skel" style="height:90px;margin-top:14px"></div></div>` : ""}`;
    } else if (q.phase === "nothing") {
      body = `<div class="card result fade-in">${ring(100, 96, "covered", "All of it understood")}
        <h2>Nothing left to quiz</h2><p>You've already shown you understand every AI-written line here.</p>
        <button class="btn" style="margin-top:14px" data-act="closeQuiz">Back to overview</button></div>`;
    } else if (q.phase === "choose") {
      body = chooseAssistant(q);
    } else if (q.phase === "error") {
      body = `<div class="card error fade-in"><h3>The quiz didn't start</h3><pre>${esc(q.message)}</pre>
        <div class="row" style="margin-top:12px"><button class="btn primary" data-act="quiz" data-path="${esc(q.scope)}">Try again</button><button class="btn" data-act="closeQuiz">Back</button></div></div>
        ${state.assistants.length ? chooseAssistant(Object.assign({}, q, { message: "Or run it with your assistant:" })) : ""}`;
    } else if (q.phase === "asking") {
      body = asking(q);
    } else if (q.phase === "done") {
      body = done(q);
    }
    return head + body;
  }

  function chooseAssistant(q) {
    const list = state.assistants || [];
    const COLORS = { "anthropic.claude-code": "#d97757", "github.copilot-chat": "#6e7bf2", "kilocode.kilo-code": "#e6b800", cursor: "#2b2b2b", "saoudrizwan.claude-dev": "#14919b", "rooveterinaryinc.roo-cline": "#7c4dcc" };
    const sub = (id) => (id === "github.copilot-chat" ? "Fills in the chat for you" : "Copies the quiz, opens the chat");
    return `<div class="card fade-in">
      <h3>Run the quiz with your assistant</h3>
      <p style="margin:0">${esc(q.message || "VS Code has no AI model to run the quiz here, so let your coding assistant ask the questions. It records your score in Grok-map when you're done.")}</p>
      <div class="assist">
        ${list
          .map(
            (a) => `<button data-act="handoff" data-id="${esc(a.id)}"><span class="mark" style="background:${COLORS[a.id] || "#555"}">${esc(a.name[0])}</span><span><div class="nm">${esc(a.name)}</div><div class="sub">${sub(a.id)}</div></span></button>`,
          )
          .join("")}
        <button data-act="handoff" data-id="copy"><span class="mark" style="background:var(--card-hi);color:var(--fg)">${ICON.copy}</span><span><div class="nm">Copy the quiz</div><div class="sub">Paste it into any AI chat</div></span></button>
      </div>
      <p class="note">Want quizzes right here? Install an extension that adds a model to VS Code, such as <a data-act="link" data-url="https://marketplace.visualstudio.com/items?itemName=GitHub.copilot-chat">GitHub Copilot</a>.</p>
    </div>`;
  }

  function quizKey(q) {
    return `${state.repo ? state.repo.path : ""}|${q.scope}|${(q.questions || []).map((x) => x.question).join("|")}`;
  }

  function asking(q) {
    const key = quizKey(q);
    if (local.key !== key) local = { key, index: 0, drafts: q.questions.map(() => "") };
    const i = Math.min(local.index, q.questions.length - 1);
    const item = q.questions[i];
    const last = i === q.questions.length - 1;
    const models = q.models || [];
    return `<div class="steps" aria-hidden="true">${q.questions.map((_, k) => `<i class="${k <= i ? "on" : ""}"></i>`).join("")}</div>
      <div class="card qcard fade-in">
        <div class="qnum">Question ${i + 1} of ${q.questions.length}${item.topic ? ` · ${esc(item.topic)}` : ""}</div>
        <div class="qtext">${rich(item.question)}</div>
        <div class="qmeta">${item.lines ? `Lines ${esc(item.lines)}` : ""}</div>
        <textarea id="answer" placeholder="Answer in your own words. Two or three sentences is plenty." aria-label="Your answer">${esc(local.drafts[i] || "")}</textarea>
        <div class="qactions">
          <span class="kbd">${navigator.platform.includes("Mac") ? "⌘" : "Ctrl"}+Enter to continue</span>
          ${i > 0 ? `<button class="btn ghost" data-act="prevQ">Back</button>` : ""}
          <button class="btn" data-act="skipQ">I don't know</button>
          <button class="btn primary" data-act="nextQ">${last ? `${ICON.check} Check my answers` : "Next"}</button>
        </div>
      </div>
      ${models.length > 1 ? `<div class="model">Model <select id="model" aria-label="Model">${models.map((m) => `<option value="${esc(m.id)}" ${m.name === q.model ? "selected" : ""}>${esc(m.name)}</option>`).join("")}</select></div>` : q.model ? `<div class="model">Questions by ${esc(q.model)}</div>` : ""}`;
  }

  function done(q) {
    const score = Math.round((q.score || 0) * 100);
    const titles = { understood: "You understand this code", partly: "Partly there", "not-yet": "Not yet" };
    const subs = {
      understood: "This code now counts as understood, by you.",
      partly: "It's recorded as skimmed. Read the explanations below, then try again later.",
      "not-yet": "Nothing changes for this code. Read the explanations below, then try again.",
    };
    const v = (s) => (s >= 1 ? ["v1", "Correct"] : s > 0 ? ["v05", "Partly"] : ["v0", "Missed"]);
    return `<div class="card result fade-in">
        ${ring(score, 108, "score", `Score ${score}%`)}
        <h2>${esc(titles[q.verdict] || "Done")}</h2><p>${esc(subs[q.verdict] || "")}</p>
        ${q.saved ? `<div class="saved">${ICON.check}<span>${esc(q.saved)}</span></div>` : `<div class="saved"><div class="orb" style="width:14px;height:14px"></div><span>Saving your result…</span></div>`}
      </div>
      ${(q.questions || [])
        .map((item, i) => {
          const g = (q.grades || [])[i] || { score: 0, feedback: "", answer: "" };
          const [cls, word] = v(g.score);
          return `<div class="card answer-card fade-in">
            <div class="row" style="align-items:flex-start"><div class="q grow">${i + 1}. ${rich(item.question)}</div><span class="verdict ${cls}">${word}</span></div>
            ${g.feedback ? `<div class="ans">${rich(g.feedback)}</div>` : ""}
            <div class="ans-label">Your answer</div><div class="ans yours">${esc((q.answers || [])[i] || "(no answer)")}</div>
            ${g.answer ? `<div class="ans-label">A good answer</div><div class="ans">${rich(g.answer)}</div>` : ""}
          </div>`;
        })
        .join("")}
      <div class="row"><button class="btn primary grow" data-act="closeQuiz">Back to overview</button></div>`;
  }

  // ------------------------------------------------------------ render + events

  function render() {
    if (!state) {
      app.innerHTML = header() + `<div class="card"><div class="skel" style="height:80px"></div></div>`;
      return;
    }
    let body;
    if (state.quiz) body = quizView();
    else if (state.phase === "norepo") body = noRepo();
    else if (state.phase === "nocli") body = noCli();
    else if (state.phase === "error") body = errorView();
    else if (state.phase === "loading" || !state.dash) body = loading();
    else body = dashboardView();
    const focusAnswer = document.activeElement && document.activeElement.id === "answer";
    app.innerHTML = header() + body;
    const ta = document.getElementById("answer");
    if (ta) {
      ta.addEventListener("input", () => {
        local.drafts[local.index] = ta.value;
        vscode.setState(local);
      });
      ta.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
          e.preventDefault();
          act("nextQ");
        }
      });
      if (focusAnswer || !ta.value) ta.focus();
    }
    const sel = document.getElementById("model");
    if (sel) sel.addEventListener("change", () => send("pickModel", { id: sel.value }));
  }

  function act(name, el) {
    const q = state && state.quiz;
    switch (name) {
      case "nextQ":
      case "skipQ": {
        if (!q || !q.questions) return;
        if (name === "skipQ") local.drafts[local.index] = "I don't know";
        if (local.index < q.questions.length - 1) {
          local.index++;
          vscode.setState(local);
          render();
        } else {
          vscode.setState(local);
          send("answers", { answers: q.questions.map((_, k) => local.drafts[k] || "") });
        }
        return;
      }
      case "prevQ":
        local.index = Math.max(0, local.index - 1);
        vscode.setState(local);
        render();
        return;
      case "quiz":
        local = { key: "", index: 0, drafts: [] };
        vscode.setState(local);
        send("quiz", { path: el ? el.dataset.path || "" : "" });
        return;
      case "useRepo":
      case "openFile":
        send(name, { path: el.dataset.path });
        return;
      case "handoff":
        send("handoff", { id: el.dataset.id });
        return;
      case "copy":
        send("copy", { text: el.dataset.text });
        return;
      case "link":
        send("link", { url: el.dataset.url });
        return;
      default:
        send(name);
    }
  }

  app.addEventListener("click", (e) => {
    const el = e.target.closest("[data-act]");
    if (!el || el.disabled) return;
    e.preventDefault();
    e.stopPropagation();
    act(el.dataset.act, el);
  });
  app.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target.classList && e.target.classList.contains("file")) {
      e.preventDefault();
      act("openFile", e.target);
    }
  });
  window.addEventListener("message", (e) => {
    if (e.data && e.data.type === "state") {
      state = e.data.state;
      render();
    }
  });
  render();
  send("ready");
})();
