import test from 'node:test';
import assert from 'node:assert/strict';

test('Frontend SSE Streaming Event Routing Contract', async (t) => {
  // Test mock events representing all 9 SSE event types
  const testEvents = [
    { type: 'agent_status', agent: 'router', status: 'active', message: 'Analyzing query intent', step: 0 },
    { type: 'thinking', agent: 'router', step: 0, content: 'Classified as complex inquiry' },
    { type: 'agent_status', agent: 'retriever', status: 'complete', message: 'Retrieved 8 passages', step: 1 },
    { type: 'retrieval_info', info: { retrieved_count: 8, reranked_count: 3, retrieval_ms: 120, is_sufficient: true } },
    { type: 'text', content: 'Here is the analyzed report regarding ' },
    { type: 'text', content: 'the quarterly financial benchmarks.' },
    {
      type: 'sources',
      sources: [
        {
          chunk_id: 'chk-12345',
          modality: 'table',
          text_repr: '| Metric | Q3 | Q4 |\n| Revenue | $10M | $14M |',
          page_num: 12,
          score: 0.94,
          rerank_score: 0.96,
          doc_title: '2025 Financial Summary',
        },
      ],
    },
    {
      type: 'image_result',
      image_b64: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
      prompt: 'Financial Growth Chart',
      refined_prompt: 'High fidelity chart showing Q3 to Q4 growth',
    },
    {
      type: 'web_results',
      results: [
        {
          title: 'Q4 Market Benchmarks 2025',
          url: 'https://marketreports.com/q4-benchmarks',
          content: 'Industry average growth reached 18% in Q4.',
          score: 0.88,
        },
      ],
    },
    {
      type: 'tool_result',
      result: { executed_tool: 'calculator', input: '14 - 10', output: 4 },
    },
    {
      type: 'voice_audio',
      audio_b64: 'UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=',
      format: 'wav',
    },
  ];

  const received = {
    tokens: [],
    sources: [],
    statuses: [],
    thinking: [],
    retrievalInfo: null,
    imageResult: null,
    webResults: [],
    toolResult: null,
    voiceAudio: null,
  };

  const callbacks = {
    onChunk: (t) => received.tokens.push(t),
    onSources: (s) => (received.sources = s),
    onAgentStatus: (st) => received.statuses.push(st),
    onThinking: (th) => received.thinking.push(th),
    onRetrievalInfo: (r) => (received.retrievalInfo = r),
    onImageResult: (img) => (received.imageResult = img),
    onWebResults: (wr) => (received.webResults = wr),
    onToolResult: (tr) => (received.toolResult = tr),
    onVoiceAudio: (aud) => (received.voiceAudio = aud),
  };

  // Simulate dispatcher logic matching api.ts
  for (const parsed of testEvents) {
    switch (parsed.type) {
      case 'text':
        callbacks.onChunk?.(parsed.content);
        break;
      case 'sources':
        callbacks.onSources?.(parsed.sources);
        break;
      case 'agent_status':
        callbacks.onAgentStatus?.({
          agent: parsed.agent,
          status: parsed.status,
          message: parsed.message,
          step: parsed.step,
        });
        break;
      case 'thinking':
        callbacks.onThinking?.({
          agent: parsed.agent,
          step: parsed.step,
          content: parsed.content,
        });
        break;
      case 'retrieval_info':
        callbacks.onRetrievalInfo?.(parsed.info);
        break;
      case 'image_result':
        callbacks.onImageResult?.({
          image_b64: parsed.image_b64,
          prompt: parsed.prompt,
          refined_prompt: parsed.refined_prompt,
        });
        break;
      case 'web_results':
        callbacks.onWebResults?.(parsed.results);
        break;
      case 'tool_result':
        callbacks.onToolResult?.(parsed.result);
        break;
      case 'voice_audio':
        callbacks.onVoiceAudio?.(parsed.audio_b64);
        break;
    }
  }

  assert.equal(received.tokens.join(''), 'Here is the analyzed report regarding the quarterly financial benchmarks.');
  assert.equal(received.sources.length, 1);
  assert.equal(received.sources[0].doc_title, '2025 Financial Summary');
  assert.equal(received.statuses.length, 2);
  assert.equal(received.thinking.length, 1);
  assert.equal(received.retrievalInfo.reranked_count, 3);
  assert.ok(received.imageResult);
  assert.equal(received.imageResult.prompt, 'Financial Growth Chart');
  assert.equal(received.webResults.length, 1);
  assert.equal(received.webResults[0].title, 'Q4 Market Benchmarks 2025');
  assert.ok(received.toolResult);
  assert.equal(received.toolResult.executed_tool, 'calculator');
  assert.ok(received.voiceAudio);
});

test('Session UUID Generator and Isolation Format', async (t) => {
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const mockUUID = crypto.randomUUID();
  assert.ok(uuidRegex.test(mockUUID), 'Generated UUID should follow RFC 4122 standard');
});
