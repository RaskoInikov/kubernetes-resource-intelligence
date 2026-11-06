# M13 Paired RAG Evaluation

## Fixed plan

- Evaluation: `m13-final-20261105`
- Evidence class: fresh local Ollama service over retained real kind/Prometheus
  incident packages
- Dataset: `1.0.0`, digest
  `c89ac9ea18c62ab6fcb3ec30164290daf560202cddd21976c4e7598e1abb97f1`
- Report digest:
  `12e797408c9134f2d4a181cab1f97bee9aeffa59e126045f23b9982bb39fa192`
- Model: `qwen3:4b`, digest
  `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`
- Prompt `1.4`; temperature zero; seed 42; 8,192-token context;
  768-token output bound; thinking disabled
- Two finding-bearing cases, two repetitions, paired RAG-off/on: eight total
  trials

## Results

Five trials returned parseable candidates and were rejected by independent
validation because generated prose contained undeclared numbers. Three RAG-on
trials failed before candidate scoring: one 600-second transport timeout and
two token-bound incomplete generations. No trial was accepted.

Validation success was zero for both modes and therefore inconclusive. Only one
pair had candidates in both modes for the remaining quality dimensions. In
that pair, supported-fact rate, citation precision/recall, finding and
uncertainty coverage, and recommendation consistency were all one in both
modes; unsupported numerical-claim rate was zero. These equal results are
inconclusive, not evidence of RAG benefit. Three missing candidate pairs remain
in every non-latency quality denominator and are reported explicitly.

Latency used all four pairs. RAG-off averaged 335.332 seconds and RAG-on
513.635 seconds. The mean paired RAG-on difference was +178.303 seconds with a
48.914-second standard deviation. Because lower latency is better, retrieval
regressed latency.

## CPU bottleneck investigation

The original full-schema finding-bearing request timed out at 900 seconds.
Compact object prompt 1.2 completed in 509.365 seconds but copied placeholders.
A template-free Qwen3.5 9B prompt timed out at 600 seconds. Positional arrays
reduced a pre-bound benchmark to 409.619 seconds, and dynamic exact-count schema
bounds produced final RAG-off completions from 296.337 to 425.400 seconds.

The optimization reduced generated structural tokens and prevented merged
findings and invalid chunk-ID shapes, but CPU generation remains too slow and
unreliable for interactive use. RAG-on added prompt tokens and had materially
worse completion reliability. Further work must create a new reviewed dataset
version if it changes the pinned model, prompt, output bound, or labels; these
results must not be overwritten or tuned in place.

## Limitations

Dataset 1.0.0 contains two retained resource-pressure incidents, not the
longer-term 20–30-case mix described in the evaluation strategy. It does not
cover healthy workloads, insufficient monitoring, resets, or all policy edge
cases. The perfect structural fact/citation scores reflect deterministic M9
assembly plus strict schema bounds; they do not excuse generated prose that
failed validation. No model-based usefulness judge was used.

## CPU-only prompt 1.5 follow-up

A focused follow-up on 2026-11-06 used the retained real CPU-throttling package
`llm-input-ui-20261102161957` and the same pinned Qwen3 4B digest, temperature,
seed, and disabled-thinking setting. Prompt 1.5 removed nonessential numerical
and identity-heavy evidence from the model-facing projection, reduced context
to 4,096 tokens, and enforced printable digit-free prose in the decoding grammar.
The independent validator and deterministic attachment of M9 facts were not
weakened.

The final identical-options pair used a 768-token ceiling. RAG-off was accepted
with zero validation issues at 930 prompt tokens, 367 output tokens, and 89.324
seconds. RAG-on was accepted with zero issues at 1,244 prompt tokens, 682 output
tokens, and 181.216 seconds. Its 16 emitted knowledge citations all resolved to
the two supplied CPU-throttling runbook chunks; RAG-off emitted none. Against
the prompt 1.4 mode means, latency fell 73.4% for RAG-off and 64.7% for RAG-on.
RAG-on still cost 91.892 seconds more than RAG-off. A separate accepted RAG-off
boundary run established that 640 tokens is its minimum tested viable ceiling
and completed in 88.485 seconds.

The retained boundary trials show why the selected ceilings differ. RAG-off at
512 tokens and both modes at insufficient higher bounds failed closed with
`ollama_incomplete`; a permissive negated-character regex admitted a control
character and failed parsing. No failed response was repaired or promoted.
Accepted paired immutable artifacts are
`results/m13-optimization/qwen3-cpu-opt15-off768-paired-20261106.json` and
`results/m13-optimization/qwen3-cpu-opt15-on768-printable-20261106.json`.
