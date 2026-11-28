---
name: grokmap
description: Quiz the user on AI-written code and track comprehension debt with the grokmap CLI. Use when the user says "quiz me", "do I understand this", "check my understanding", "comprehension debt", "grokmap", or asks for a map of which code nobody understands. Also offer a short quiz (one line, never forced) after you finish a substantial change the user will commit, such as a new feature, a non-trivial fix or a refactor.
---

# Grok-map: pay down comprehension debt

Grok-map measures **comprehension debt**: code an AI agent wrote that no person on the team has shown they understand. Your job in this skill is to run short, honest quizzes and record the results, so the team's map of what it understands stays true.

## Setup (once per machine)

Check the CLI is available, and install it if not:

```bash
grokmap --version || pipx install grokmap || pip install --user grokmap
```

If none of those work, `uvx grokmap <command>` runs it without installing. In a repo that has never used Grok-map, run `grokmap init` (it adds `.grokmap.toml`, the ledger and a merge rule) and tell the user what it created.

If the Grok-map MCP tools are connected (`comprehension_risk`, `quiz_brief`, `record_understanding`…), use them instead of the CLI: they return the same data as structured results. Before you change a file, `comprehension_risk` tells you how carefully to tread: at *high* or *very high*, keep the diff small, explain what you changed and why, and offer a quiz afterwards.

## When to use it

| The user… | Do this |
|---|---|
| asks to be quizzed on a file, folder or change | `grokmap quiz <path>` (or `--uncommitted` / `--diff main`), then run the quiz below |
| just accepted a substantial change from you | Offer once, in one line: "Want a 2-minute quiz on this before you commit? It keeps Grok-map's map honest." If they decline, drop it. |
| asks how much of the code is understood, or where the risk is | `grokmap status`; for the visual map `grokmap report --open` |
| asks who knows a part of the code | `grokmap who <path>` |
| is about to open or merge a PR | `grokmap diff --base main` shows the AI lines the branch adds and how many are understood; offer a quiz on the unchecked ones |
| asks how much of the code AI writes, or how that changed | `grokmap trend` |
| wants it in CI | point them to the README's GitHub Action section, or run `grokmap check` |

Do not offer a quiz after trivial edits (typos, renames, formatting, one-line config).

## Running a quiz

1. **Get the brief.** Pick the narrowest scope that matches what the user means:
   - code you just wrote and they have not committed: `grokmap quiz --uncommitted`
   - a branch or PR: `grokmap quiz --diff main` (use the real base branch)
   - a file or folder: `grokmap quiz src/payments/`

   The brief lists the exact lines the person has not yet shown they understand, and ends its instructions with the exact `grokmap mark …` command to run afterwards. If it says "Nothing to quiz", tell the user and stop.

2. **Ask questions one at a time.** Ask the number of questions the brief says (usually 3). Wait for each answer before asking the next. Never show the answer or the relevant code inside the question.
   Ask about what matters when this code breaks: behavior on edge cases, why an ordering or check exists, what a failure looks like, where they would look for a given bug, what would break if a line were removed. Do not ask trivia that re-reading a name answers.

3. **Grade honestly.** For each answer: 1 = correct and explains why, 0.5 = partly right or vague, 0 = wrong or "I don't know". After each answer, give the correct answer in one or two sentences. Be kind and plain; a low score is useful information, not a failure.

4. **Record the result.** Score = mean of the grades. Run the `grokmap mark` command from the brief with `--score <score> --method quiz`. Then tell the user their score, and if it is below 0.7, which part to reread.

   - If the person prefers to explain the change in their own words instead of a quiz, grade the explanation the same way and use `--method explain`.
   - If they only want to note that they skimmed it, use `--method review` (counts as half-understood).

5. **Remind them to commit the ledger** (`.grokmap/ledger.jsonl`) with their change, so the rest of the team sees it.

## Rules

- **Never record a result the person did not earn.** No marking without their answers, no rounding up, no marking on someone else's behalf. `--who` is only for when the user explicitly tells you who is answering.
- **Never mark your own code as understood** because you wrote it. The ledger is about people.
- Keep it short. A quiz is 2 to 5 questions. If the brief says it was cut down, finish this round and offer another later.
- If the user is frustrated or busy, stop the quiz at once and do not record anything.
- Grok-map only reads git history and local files. Do not send code anywhere to grade answers; grade them yourself.

## Reading `grokmap status`

- **Comprehension debt**: unread AI lines plus half of skimmed and fading lines, as a share of all meaningful lines.
- **understood / fading / skimmed / nobody checked**: AI-written lines by state. Fading means it was understood long ago (180 days by default) and probably needs a refresher.
- **Riskiest files**: where a quiz pays down the most debt. Suggest starting with the top one that sits on a critical path.
