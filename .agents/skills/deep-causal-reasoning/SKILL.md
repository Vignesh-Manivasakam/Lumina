---
name: deep-causal-reasoning
description: >
  Performs structured causal analysis and hypothesis testing over evidence retrieved through
  Lumina's RAG pipeline (documents, structured metrics, logs, incident reports, tickets) to
  answer "why" questions: root-cause investigations, anomaly explanations, post-mortems, and
  driver analysis for business or technical metric changes. Generates a broad hypothesis space
  before searching (to avoid confirmation bias), actively retrieves disconfirming as well as
  confirming evidence for each hypothesis, applies explicit causal-inference heuristics
  (temporal precedence, mechanism plausibility, dose-response, confound-checking) to
  distinguish causation from mere correlation, and returns a ranked, transparent reasoning
  chain with calibrated confidence levels and an explicit statement of residual uncertainty.
  Use this skill whenever a user asks "why did X happen," "what caused," "root cause of,"
  "explain the drop/spike/change in," requests a post-mortem, incident review, or 5-whys
  analysis, or asks Lumina to test a specific hypothesis against the knowledge base. Do not use
  it for simple factual lookups that have no causal "why" component.
category: analytical-reasoning
tags:
  - causal-inference
  - root-cause-analysis
  - hypothesis-testing
  - rag
  - reasoning
  - enterprise
  - post-mortem
version: 1.0.0
author: Lumina Platform Team
requires_tools:
  - vector_search
  - structured_data_query
  - citation_engine
parameters_schema:
  type: object
  required:
    - question
  properties:
    question:
      type: string
      description: The causal question or metric anomaly to investigate.
    scope:
      type: object
    known_hypotheses:
      type: array
      items: { type: string }
    max_hypotheses:
      type: integer
      default: 5
    confidence_threshold:
      type: string
      enum: [low, medium, high]
      default: low
    output_format:
      type: string
      enum: [markdown, json]
      default: markdown
---

# Deep Causal Reasoning & Hypothesis Testing

## 1. Purpose & Trigger Conditions
Investigates causal drivers and root causes of anomalies, incidents, and performance shifts using structured empirical hypothesis testing and observational evidence.

## 2. Confidence Rubric
- **Confirmed**: Temporal precedence verified, specific mechanism plausible, magnitude match holds, disconfirming searches found no contradictions, and confounds ruled out.
- **Likely**: Strong empirical evidence with minor gaps in magnitude precision.
- **Possible**: Correlated in time but unproven mechanism or unaddressed confounds.
- **Unlikely / Ruled Out**: Contradicted by temporal order or direct evidence.
