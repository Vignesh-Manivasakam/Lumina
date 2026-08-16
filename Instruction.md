# Ruflo — Claude Code Configuration

## Rules

- Do what has been asked; nothing more, nothing less
- NEVER create files unless absolutely necessary — prefer editing existing files
- NEVER create documentation files unless explicitly requested
- NEVER save working files or tests to root — use `/src`, `/tests`, `/docs`, `/config`, `/scripts`
- ALWAYS read a file before editing it
- NEVER commit secrets, credentials, or .env files
- NEVER add a `Co-Authored-By` trailer to user commits unless this project's `.claude/settings.json` has `attribution.commit` set (#2078). The Claude Code Bash tool may suggest one in its default commit-message template — ignore it. `Co-Authored-By` is semantic authorship attribution under git/GitHub convention; the tool is the facilitator, not a co-author.
- Keep files under 500 lines
- Validate input at system boundaries

## Ruflo Capability Brain & Implementation Loop

Ruflo is the coordination ledger and policy decision point. Claude Code is the
executor: after a Ruflo coordination call, continue implementing the task.

When it is registered, call
`guidance_brain({ mode: "recommend", task: "..." })` before complex Ruflo
work. Use its live registry instead of guessing tool names. Treat
`registered`, `configured`, `reachable`, `healthy`, and `authorized`
as separate facts. If the brain is unavailable, continue with the compatible
`guidance_recommend` tool, CLI discovery, and repository instructions.

Follow the returned loop:

1. Recall memory and ADR constraints.
2. Inspect source, runtime, dependencies, policy, and health.
3. Route to the smallest capable topology, agents, skills, and tools.
4. Plan acceptance criteria, safety envelope, ownership, and validation.
5. Execute in isolated scopes; the coding agent performs the work.
6. Test focused, regression, and failure paths.
7. Validate types, security, policy, compatibility, and artifacts.
8. Benchmark a source-bound candidate against a source-bound baseline.
9. Optimize measured bottlenecks without weakening safety.
10. Bind claims and evidence to exact source/build receipts.
11. Reconcile concurrent handoffs and disclose limitations.
12. Publish only through a separately authorized release gate.

### Concurrency and authority

- Never allow two writers in one worktree; give each writing agent an isolated
  worktree and explicit file ownership.
- Read-only research may run concurrently and report findings to the owner.
- Only the integration owner edits shared manifests and lockfiles or reconciles
  overlapping changes.
- A child may drop capabilities but cannot add tools, network, secrets, spend,
  concurrency, namespaces, or delegation depth.
- A lease or claim coordinates ownership; it does not authorize a side effect.
- Darwin, Flywheel, MetaHarness, memory, and neural systems may propose or
  evaluate candidates but cannot self-promote or expand their SafetyEnvelope.
- Bind tests, benchmarks, policy decisions, and release evidence to an exact
  commit or immutable dirty-worktree snapshot.

## Agent Comms (SendMessage-First Coordination)

Named agents coordinate via `SendMessage`, not polling or shared state.

```
Lead (you) ←→ architect ←→ developer ←→ tester ←→ reviewer
              (named agents message each other directly)
```

### Spawning a Coordinated Team

```javascript
// ALL agents in ONE message, each knows WHO to message next
Agent({ prompt: "Research the codebase. SendMessage findings to 'architect'.",
  subagent_type: "researcher", name: "researcher", run_in_background: true })
Agent({ prompt: "Wait for 'researcher'. Design solution. SendMessage to 'coder'.",
  subagent_type: "system-architect", name: "architect", run_in_background: true })
Agent({ prompt: "Wait for 'architect'. Implement it. SendMessage to 'tester'.",
  subagent_type: "coder", name: "coder", run_in_background: true })
Agent({ prompt: "Wait for 'coder'. Write tests. SendMessage results to 'reviewer'.",
  subagent_type: "tester", name: "tester", run_in_background: true })
Agent({ prompt: "Wait for 'tester'. Review code quality and security.",
  subagent_type: "reviewer", name: "reviewer", run_in_background: true })

// Kick off the pipeline
SendMessage({ to: "researcher", summary: "Start", message: "[task context]" })
```

### Patterns

| Pattern | Flow | Use When |
|---------|------|----------|
| **Pipeline** | A → B → C → D | Sequential dependencies (feature dev) |
| **Fan-out** | Lead → A, B, C → Lead | Independent parallel work (research) |
| **Supervisor** | Lead ↔ workers | Ongoing coordination (complex refactor) |

### Rules

- ALWAYS name agents — `name: "role"` makes them addressable
- ALWAYS include comms instructions in prompts — who to message, what to send
- Spawn ALL agents in ONE message with `run_in_background: true`
- After spawning, continue independent local work; wait only when a dependency
  genuinely blocks progress
- Do not poll repeatedly — agents message back or complete automatically
- Give every writing agent an isolated worktree and a non-overlapping file scope

## Swarm & Routing

### Config
- **Topology**: hierarchical-mesh (anti-drift)
- **Max Agents**: 15
- **Memory**: hybrid
- **HNSW**: Enabled
- **Neural**: Enabled

```bash
npx @claude-flow/cli@latest swarm init --topology hierarchical --max-agents 8 --strategy specialized
```

### Agent Routing

| Task | Agents | Topology |
|------|--------|----------|
| Bug Fix | researcher, coder, tester | hierarchical |
| Feature | architect, coder, tester, reviewer | hierarchical |
| Refactor | architect, coder, reviewer | hierarchical |
| Performance | perf-engineer, coder | hierarchical |
| Security | security-architect, auditor | hierarchical |

### When to Swarm
- **YES**: 3+ files, new features, cross-module refactoring, API changes, security, performance
- **NO**: single file edits, 1-2 line fixes, docs updates, config changes, questions

### 3-Tier Model Routing

| Tier | Handler | Use Cases |
|------|---------|-----------|
| 1 | Agent Booster (WASM) | Simple transforms — skip LLM, use Edit directly |
| 2 | Haiku | Simple tasks, low complexity |
| 3 | Sonnet/Opus | Architecture, security, complex reasoning |

## Memory & Learning

### Before Any Task
```bash
npx @claude-flow/cli@latest memory search --query "[task keywords]" --namespace patterns
npx @claude-flow/cli@latest hooks route --task "[task description]"
```

### After Success
```bash
npx @claude-flow/cli@latest memory store --namespace patterns --key "[name]" --value "[what worked]"
npx @claude-flow/cli@latest hooks post-task --task-id "[id]" --success true --store-results true
```

### MCP Tools (use `ToolSearch("keyword")` to discover)

| Category | Key Tools |
|----------|-----------|
| **Memory** | `memory_store`, `memory_search`, `memory_search_unified` |
| **Bridge** | `memory_import_claude`, `memory_bridge_status` |
| **Swarm** | `swarm_init`, `swarm_status`, `swarm_health` |
| **Agents** | `agent_spawn`, `agent_list`, `agent_status` |
| **Hooks** | `hooks_route`, `hooks_post-task`, `hooks_worker-dispatch` |
| **Security** | `aidefence_scan`, `aidefence_is_safe`, `aidefence_has_pii` |
| **Hive-Mind** | `hive-mind_init`, `hive-mind_consensus`, `hive-mind_spawn` |

### Background Workers

| Worker | When |
|--------|------|
| `audit` | After security changes |
| `optimize` | After performance work |
| `testgaps` | After adding features |
| `map` | Every 5+ file changes |
| `document` | After API changes |

```bash
npx @claude-flow/cli@latest hooks worker dispatch --trigger audit
```

## Agents

**Core**: `coder`, `reviewer`, `tester`, `planner`, `researcher`
**Architecture**: `system-architect`, `backend-dev`, `mobile-dev`
**Security**: `security-architect`, `security-auditor`
**Performance**: `performance-engineer`, `perf-analyzer`
**Coordination**: `hierarchical-coordinator`, `mesh-coordinator`, `adaptive-coordinator`
**GitHub**: `pr-manager`, `code-review-swarm`, `issue-tracker`, `release-manager`

Any string works as a custom agent type.

## Build & Test

- ALWAYS run tests after code changes
- ALWAYS verify build succeeds before committing

```bash
npm run build && npm test
```

## CLI Quick Reference

```bash
npx @claude-flow/cli@latest init --wizard           # Setup
npx @claude-flow/cli@latest swarm init --v3-mode     # Start swarm
npx @claude-flow/cli@latest memory search --query "" # Vector search
npx @claude-flow/cli@latest hooks route --task ""    # Route to agent
npx @claude-flow/cli@latest doctor --fix             # Diagnostics
npx @claude-flow/cli@latest security scan            # Security scan
npx @claude-flow/cli@latest performance benchmark    # Benchmarks
```

26 commands, 140+ subcommands. Use `--help` on any command for details.

## Setup

```bash
claude mcp add claude-flow -- npx -y ruflo@latest mcp start
npx ruflo@latest doctor --fix
```

> The background `daemon` is optional. It runs interval workers that each spawn
> a headless `claude` session, so it consumes tokens continuously. Start it only
> if you want those sweeps: `npx ruflo@latest daemon start` (self-stops after 12h
> by default; `--ttl 0` to disable, `daemon status --all` to audit running daemons).

**Agent tool** handles execution (agents, files, code, git). **MCP tools** handle coordination (swarm, memory, hooks). **CLI** is the same via Bash.

## Graphify Memory & Knowledge Graph

- **Query Graph**: Use `graphify god-nodes`, inspect `graphify-out/GRAPH_REPORT.md`, or read `graphify-out/graph.json` for code dependencies and community hubs.
- **Update Graph**: Run `graphify extract . --code-only` or `graphify cluster-only .`
- **Hook Guard Notice**: Do NOT enable `graphify hook install` or `graphify claude install` `PreToolUse` hooks, as `hook-guard` intercepts standard Claude Code tool declarations (`Bash`, `Read`, `Glob`, `Grep`) causing tool invocation routing errors.



# Claude Code Implementation Prompt — Ruflo Multi-Agent Workflow

## Primary Instruction

Use **Ruflo** throughout this task to coordinate the implementation, analysis, testing, and review work.

Do **not** start implementing immediately.

The implementation must follow the workflow below in order. Do not skip phases.

---

# Phase 1 — Understand and Audit the Existing Codebase

Before making any code changes:

1. Inspect the complete relevant codebase.
2. Understand:

   * Project structure
   * Frontend architecture
   * Backend architecture
   * Data flow
   * API contracts
   * Database/data models
   * Existing components/modules
   * Existing state management
   * Existing error handling
   * Authentication/authorization if applicable
   * Existing tests
   * Existing test infrastructure
   * Build and deployment configuration
   * Existing documentation
3. Identify existing patterns and conventions that the new implementation must follow.
4. Identify technical debt, risks, coupling, and areas that could be affected by the requested change.
5. Search for existing functionality that may already partially solve the requirement. **Do not duplicate existing functionality.**
6. Identify all files/modules that are likely to be affected.

### Ruflo Requirement

Use Ruflo agents where appropriate during this investigation.

Assign agents according to their strengths/skills. For example:

* Codebase exploration agent
* Frontend architecture agent
* Backend architecture agent
* Data/model analysis agent
* Testing/QA agent
* Security/reliability review agent

Agents should **share their findings** rather than independently making assumptions.

### Deliverable

Before implementation, produce a concise:

**CODEBASE ASSESSMENT**

containing:

* Current architecture
* Relevant existing functionality
* Important files/modules
* Existing patterns to follow
* Dependencies
* Risks
* Potential conflicts
* Testing strategy already present
* Recommended implementation approach

Do not modify production code during this phase unless absolutely necessary for investigation tooling.

---

# Phase 2 — Implementation Plan

After understanding the codebase, create a detailed implementation plan.

Do not start coding until the plan is clear.

The plan should first define a **Vertical Slice**.

## Vertical Slice First

Implement the smallest complete end-to-end version of the feature.

The vertical slice should demonstrate the complete flow:

**User → Frontend → API/Backend → Processing → Data → Response → Frontend → User**

The vertical slice must be functional enough to validate the architecture and integration before splitting the remaining work.

Explain:

* What the vertical slice contains
* Which frontend components are involved
* Which backend/API components are involved
* Which data/model changes are involved
* How data flows through the system
* How it will be tested

---

# Phase 3 — Decompose the Remaining Work

After defining the vertical slice, divide the remaining implementation into **Frontend** and **Backend** work.

## Frontend

Further decompose the frontend work into logical responsibilities such as:

* Data
* Models/types
* API/client layer
* State management
* Business/process logic
* Components
* UI
* Tables
* Text/content rendering
* Image rendering
* Video rendering
* Loading states
* Empty states
* Error states
* Validation
* Accessibility
* Integration
* Tests

Do not blindly create every category if it doesn't apply. Use the categories that match the actual architecture.

## Backend

Further decompose backend work into logical responsibilities such as:

* API/routes/controllers
* Data
* Models/entities
* Database
* Validation
* Business/process logic
* Services
* External integrations
* Error handling
* Security
* Logging/observability
* Performance
* Tests

Again, adapt the decomposition to the actual codebase.

---

# Phase 4 — Ruflo Agent Assignment

Use Ruflo to parallelize work where it is safe to do so.

Do not create unnecessary agents.

Each agent must have:

1. A clearly defined responsibility.
2. The necessary skills/context for that responsibility.
3. Explicit input and expected output.
4. Clear boundaries regarding which files/modules it can modify.
5. Testing responsibilities.
6. Instructions to follow existing project conventions.

Example agent structure:

| Agent     | Responsibility       | Scope               |
| --------- | -------------------- | ------------------- |
| Architect | Overall architecture | Read-only initially |
| Frontend  | UI/components        | Frontend modules    |
| Backend   | API/services         | Backend modules     |
| Data      | Models/data layer    | Data/model modules  |
| QA        | Test strategy        | Tests + validation  |
| Reviewer  | Code review          | Read-only           |

### Important

Do not allow multiple agents to modify the same files simultaneously unless there is a clear coordination strategy.

Before merging agent work:

* Review the changes.
* Resolve conflicts.
* Verify integration.
* Run tests.

---

# Phase 5 — Implementation

Implement the feature in this order:

### Step 1 — Vertical Slice

Complete and validate the smallest end-to-end flow.

### Step 2 — Frontend

Implement the remaining frontend responsibilities.

### Step 3 — Backend

Implement the remaining backend responsibilities.

### Step 4 — Integration

Connect and validate the complete flow.

### Step 5 — Refinement

Improve:

* Error handling
* Validation
* Edge cases
* Performance
* Accessibility
* Security
* Maintainability
* Logging
* User experience

Do not introduce unnecessary architectural changes outside the scope of this feature.

---

# Phase 6 — Testing

Testing is a **critical requirement** for this task.

There are two different levels of testing required.

## A. Automated Testing

Create or update appropriate:

* Unit tests
* Integration tests
* API tests
* Component tests
* End-to-end tests

Use the existing testing framework and conventions of the repository.

Do not remove or weaken existing tests just to make the implementation pass.

Run:

* Existing test suite
* New tests
* Type checking
* Linting
* Build verification

Fix failures rather than simply reporting them.

---

# Phase 7 — User-Level / Functional Testing

Automated tests are **not sufficient**.

I also need complete testing from the perspective of a real user.

Think of yourself as a QA engineer manually using the application.

Test the complete feature through the actual user-facing flow.

Test all relevant content types, including:

* Text
* Tables
* Images
* Videos
* Links
* Long content
* Short content
* Empty content
* Missing content
* Invalid content
* Large content
* Multiple items
* Single items
* Loading states
* Error states
* Retry flows
* Boundary cases

Do not assume that because the API or unit tests pass, the feature works correctly for the user.

Verify:

* UI rendering
* Layout
* Data correctness
* API integration
* State transitions
* User interactions
* Error messages
* Loading behavior
* Empty states
* Responsive behavior where applicable
* Browser/user-facing behavior
* End-to-end data flow

If browser automation or an available UI testing tool is present, use it.

If something cannot be tested automatically, explicitly document the limitation and perform the closest practical validation available.

---

# Phase 8 — Test Evidence / Markdown Report

Create a Markdown report containing the results of the testing.

For every important user scenario, document:

| Question / Scenario      | Test Data | Expected Result | Actual Result | Status |
| ------------------------ | --------- | --------------- | ------------- | ------ |
| Can the user...?         | ...       | ...             | ...           | PASS   |
| Does text render...?     | ...       | ...             | ...           | PASS   |
| Does a table render...?  | ...       | ...             | ...           | PASS   |
| Does an image render...? | ...       | ...             | ...           | PASS   |
| Does video work...?      | ...       | ...             | ...           | PASS   |

The report should answer:

1. **What did we test?**
2. **How did we test it?**
3. **What data/input did we use?**
4. **What did we expect?**
5. **What actually happened?**
6. **Did it pass or fail?**
7. **If it failed, what was the root cause?**
8. **Was the issue fixed and retested?**

Include both:

### Automated Test Results

* Unit tests
* Integration tests
* E2E tests
* Type checks
* Lint
* Build

### User-Level Test Results

Document the actual scenarios tested from the user's perspective.

---

# Phase 9 — Independent Review

Before considering the work complete, use a Ruflo agent as an **independent reviewer**.

The reviewer should NOT assume that the implementation is correct.

Ask the reviewer to inspect:

* Requirements
* Architecture
* Implementation
* Code quality
* Security
* Error handling
* Edge cases
* Tests
* User experience
* Test coverage
* Potential regressions
* Missing scenarios

The reviewer should specifically look for things that the implementation agent may have overlooked.

If the reviewer identifies issues:

1. Fix them.
2. Re-run the relevant tests.
3. Re-run the affected user-level scenarios.
4. Update the Markdown test report.

---

# Phase 10 — Final Verification

Before reporting completion, verify that:

* [ ] Original requirements are satisfied
* [ ] Vertical slice works end-to-end
* [ ] Frontend implementation is complete
* [ ] Backend implementation is complete
* [ ] Data/model changes are correct
* [ ] Automated tests pass
* [ ] Integration tests pass
* [ ] E2E tests pass where applicable
* [ ] Type checking passes
* [ ] Lint passes
* [ ] Build succeeds
* [ ] User-level testing is complete
* [ ] Text rendering is tested
* [ ] Table rendering is tested
* [ ] Image rendering is tested
* [ ] Video rendering is tested
* [ ] Loading states are tested
* [ ] Empty states are tested
* [ ] Error states are tested
* [ ] Edge cases are tested
* [ ] Independent Ruflo review is complete
* [ ] Review findings are resolved
* [ ] Markdown test report is updated
* [ ] No unrelated code was unnecessarily modified

---

# Final Response

At the end, provide a concise implementation summary containing:

## Implementation Summary

* What was implemented
* Main architectural changes
* Frontend changes
* Backend changes
* Data/model changes

## Ruflo Agent Summary

* Agents used
* Responsibility of each agent
* Important findings from each agent

## Testing Summary

* Automated tests
* Integration tests
* E2E tests
* User-level tests
* Build/type/lint results

## User Scenario Coverage

Explicitly state whether the following were tested:

* Text
* Tables
* Images
* Videos
* Loading
* Empty states
* Errors
* Edge cases

## Review Summary

* Independent review result
* Issues found
* Issues fixed
* Remaining risks

## Test Report

Create/update a Markdown file such as:

`docs/testing/<feature-name>-test-report.md`

The Markdown report is mandatory and must contain the detailed scenarios, questions, test data, expected results, actual results, and PASS/FAIL status.

---

# Critical Rules

1. **Do not code before understanding the codebase.**
2. **Do not skip the vertical slice.**
3. **Do not blindly parallelize work.**
4. **Agents must have clearly defined responsibilities.**
5. **Avoid multiple agents modifying the same files simultaneously.**
6. **Follow existing architecture and coding conventions.**
7. **Do not consider unit tests alone sufficient.**
8. **Test the feature as a real user would use it.**
9. **Test text, tables, images, videos, and other relevant content types.**
10. **Every failure must either be fixed or explicitly documented.**
11. **After fixes, retest the affected scenario.**
12. **Use an independent agent for final review.**
13. **Do not claim something was tested if it was not actually tested.**
14. **Do not mark the task complete until the Markdown test report is created and updated.**
15. **Keep unrelated changes out of the implementation.**

Start with **Phase 1 — Codebase Assessment**. Do not begin implementation yet.
