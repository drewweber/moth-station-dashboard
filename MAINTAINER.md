# Maintainer Playbook

## Quick PR Review Request

When you want Codex to review pending pull requests, use this prompt:

```text
Review pending PRs and suggest action. Do not merge or comment until I confirm.
```

Codex should then:

1. List open PRs with title, author, branch, status checks, review status, and
   whether the branch is behind `main`.
2. Inspect each PR's changed files, commits, and description.
3. For code changes, fetch the PR branch and review it against current `main`.
4. Run cheap checks when practical:

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q mothdash
python3 -m mothdash render
```

5. Report a clear recommendation for each PR:

- `Merge`: checks pass, branch is current, scope is understandable, and no
  blocking findings remain.
- `Comment`: changes are directionally fine but need explanation, screenshots,
  tests, PR-description updates, or small fixes.
- `Request rebase`: branch is stale, conflicts with current `main`, or GitHub
  says it is not mergeable.
- `Needs review`: PR is too large, risky, or unclear to merge without human
  inspection.
- `Close/split`: PR mixes unrelated work or would be safer as smaller PRs.

Codex should include suggested comment text for any `Comment`, `Request
rebase`, or `Close/split` recommendation.

## Public Actions Require Confirmation

Codex should not merge, close, approve, request changes, or post comments
without an explicit follow-up instruction such as:

```text
Merge PR #12.
Post that comment on PR #14.
Request rebase on PR #15.
```

Before taking a public action, Codex should restate the exact action and target
PR number.

## Review Priorities

Prioritize blockers in this order:

1. Data correctness: species-only semantics, moth-session dates, station
   inclusion/exclusion, first-record language, and network union math.
2. Live mode behavior: current 12pm-to-12pm event handling, species-rank
   filtering, station activity, and iNaturalist query bounds.
3. Performance and free-tier fit: homepage size, hidden media/cards, workflow
   frequency, API volume, and Cloudflare/GitHub Actions limits.
4. Reviewability: coherent scope, useful PR description, test evidence,
   screenshots for visible changes, and no generated or database artifacts.
5. UI quality: mobile fit, sticky/navigation behavior, readable charts, and
   accessible labels/tooltips.

Use a code-review stance: findings first, ordered by severity, with file and
line references where possible. Keep summaries brief.
