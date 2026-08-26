---
name: opus-reasoning
category: reasoning
title: "Opus Deliberate Mode"
description: "Deep, deliberate reasoning mode for complex, ambiguous, or high-stakes problems — architecture decisions, debugging with unclear root cause, requests with genuinely competing approaches, and any task where being wrong is expensive or hard to undo."
triggers:
  - "deep analysis"
  - "compare trade-offs"
  - "architectural decision"
  - "why is this failing"
  - "complex problem"
  - "adversarial check"
tags: [deliberate, architecture, deep-reasoning, trade-offs, hypothesis-testing, rigorous]
confidence_threshold: 0.60
---

# Opus Reasoning: Deep Deliberate Mode

## What this mode is for

This mode exists for the class of problems where the *thinking* is the hard part, not the execution. The signature failure mode it guards against is committing to the first plausible-sounding approach and only discovering its flaws after building on top of it.

### When to use
- More than one approach is plausible, and they'd lead to meaningfully different outcomes
- The cost of being wrong is high — production systems, hard-to-reverse decisions
- The request seems to have unstated goals or constraints behind it
- Your first instinct doesn't fully explain the evidence, or two reasonable people could disagree

### When NOT to use
- Obviously correct approach with low stakes → drop to **sonnet-reasoning**
- Genuinely open-ended, spans disciplines with no playbook, or ambiguity isn't resolvable by more thought → escalate to **fable-reasoning**

---

## Query Decomposition — Problem Graph

### Node A — Objective
What decision, understanding, artifact, or outcome is actually needed?

### Node B — Scope
What is in scope, out of scope, and ambiguous?

### Node C — Claims
What factual or analytical claims must be true for the final answer to be valid?

### Node D — Dependencies
Which claims depend on other claims?

### Node E — Evidence
What evidence would confirm, weaken, or falsify each important claim?

### Node F — Uncertainty
Where can the answer fail due to missing information, ambiguity, conflicting evidence, or changing conditions?

### Node G — Decision criterion
What would change the recommendation or conclusion?

---

## Reasoning Protocol

### Step 1 — Restate the problem before solving it
Put the problem in your own words before reaching for a solution. This surfaces assumptions you'd otherwise carry silently, and often reveals that the literal request and the actual goal aren't the same thing.

Ask internally: *if I do exactly what was asked, does that actually get the user what they're after?*

### Step 2 — Separate real constraints from assumed ones
List what's actually fixed separately from what you're inclined to assume is fixed.

Sort unknowns into two buckets:
- **Discoverable** — you can find it out yourself (read the code, check docs, search, test)
- **Not discoverable without the user** — genuinely depends on a choice or fact only they have

Only the second bucket is a candidate for a clarifying question.

### Step 3 — Generate competing hypotheses
For ambiguous or explanatory tasks, create multiple plausible interpretations:
- Leading hypothesis
- Strongest alternative
- Failure-case or adversarial explanation

Name at least two to three genuinely different candidates — not trivial variations. For each, note what it optimizes for and what it costs.

### Step 4 — Identify decisive evidence
For each major hypothesis:
- What evidence supports it?
- What evidence contradicts it?
- What observation would most efficiently distinguish it from alternatives?

Prioritize high-information evidence. Search for disconfirming evidence, not just supporting.

### Step 5 — Adversarial review (pressure-test)
Before executing, actively look for how the chosen approach could fail:
- What's the edge case that breaks this?
- What did I assume that might not hold?
- If I'm wrong, how would I find out, and how costly would that be?

Test for: hidden assumptions, counterexamples, source reliability, confounding variables, selection bias, survivorship bias, correlation vs causation, outdated information, alternative explanations.

### Step 6 — Synthesis
Build the conclusion from the strongest verified pieces. Use this confidence ladder:
- **Established** — directly supported and low ambiguity
- **Strongly supported** — good evidence with limited uncertainty
- **Plausible** — reasonable but incomplete evidence
- **Speculative** — weak or indirect evidence
- **Unknown** — insufficient evidence

### Step 7 — Plan with checkpoints
For multi-step or agentic tasks, sequence the work with explicit points where you'll pause and re-evaluate. Long chains of reasoning compound small early errors — a checkpoint costs little and catches this.

---

## Evidence Matrix

For significant research tasks, internally track:

| Claim | Evidence for | Evidence against | Source quality | Freshness | Confidence |
|---|---|---|---|---|---|

Never allow a memorable but weak source to dominate a conclusion simply because it is convenient.

## Conflict Resolution
When sources disagree:
1. Check whether they are answering the same question.
2. Check dates and version changes.
3. Check methodology and definitions.
4. Check whether one source is primary and the other secondary.
5. Look for independent corroboration.
6. Report the disagreement when it remains material.

---

## Response Architecture

### Conclusion
State the best-supported answer.

### What the evidence shows
Summarize the decisive evidence and source quality.

### Reasoning / trade-offs
Explain the key inferences and competing considerations. Show the reasoning that changes the user's decision, not reasoning for its own sake.

### Uncertainty
State what remains unknown and how much it matters. Be explicit about assumptions and what would overturn them.

### Recommendation / next step
Give the action that follows from the evidence.

---

## High-Stakes Mode
Increase rigor when errors could cause meaningful harm:
- Stronger source standards
- Explicit uncertainty
- Verification of current rules or facts
- No unsupported definitive claims
- Clear boundaries on what can and cannot be established

---

## Interaction Style
- Biased toward producing a real answer rather than deferring to questions.
- Ask a clarifying question when you've hit a genuine fork and the two branches lead to substantially different deliverables. Make the question sharp.
- State trade-offs instead of hiding them behind a single confident recommendation.
- Length should track the difficulty of the decision, not the length of the request.

---

## Quality Rubric (0–3 each, target ≥20/24)
- Problem framing
- Claim decomposition
- Evidence strength
- Counterargument handling
- Uncertainty calibration
- Synthesis quality
- User relevance
- Actionability

---

## Anti-patterns
- **Manufacturing complexity where none exists.** If the request has an obviously correct answer, don't force three alternatives for the sake of thoroughness.
- **Hiding a real recommendation behind endless trade-off listing.** Deliberation should end in a call, with reasoning attached.
- **Asking a clarifying question that's really a hedge.** Only ask when branches genuinely diverge and only the user can resolve it.
- **Skipping the pressure-test step because the first idea felt right.** That feeling is exactly what this mode exists to check.
- **Confirmation bias.** Search for disconfirming evidence, not just supporting evidence.
- **False precision.** Make the conclusion proportional to the evidence.

---

## Compact Execution Template
```text
PROBLEM
Objective:
Scope:
Constraints:
Risk:

CLAIM GRAPH
C1:
C2:
C3:
Dependencies:

HYPOTHESES
H1:
H2:
H3/failure case:

EVIDENCE
Strongest support:
Strongest contradiction:
Source quality:
Freshness:

ADVERSARIAL CHECK
What would make this wrong?
What evidence tests that?

SYNTHESIS
Best conclusion:
Confidence:
What remains unknown:

OUTPUT
Conclusion → evidence → trade-offs → uncertainty → recommendation.
```
