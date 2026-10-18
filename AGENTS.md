# AGENTS.md

This file defines durable repository guidance for the meeting-minutes product in this repo.

## Scope

- This repository is for a transcript-to-structured-minutes pipeline.
- Input is transcript data, not raw audio. Do not add ASR/transcription scope unless explicitly requested.
- The product goal is trustworthy minutes with traceable evidence, not a generic summary chatbot.

## Core Product Rules

- Preserve the fixed processing flow unless a change is explicitly requested:
  `transcript input -> cleanup/polish -> meeting-type classification -> template selection -> generation -> verification -> render/export`
- Final user-facing output must follow the selected meeting template and always include:
  `议题 / 结论 / 待办`
- Supported meeting types are:
  `project_sync`, `decision_review`, `issue_triage`, `brainstorming`, `interview_research`, `general_meeting`
- Classification affects template choice and extraction focus only. It must not weaken any safety or verification rule.

## Truthfulness And Evidence Rules

- Every generated conclusion, todo, or key point must be traceable to source transcript evidence.
- Never invent `seg_id`, speaker identity, owner, due date, number, decision, or consensus.
- `owner` can only use speaker values that appear in the input transcript.
- If the relevant source segment has missing speaker information, `owner` must be `null` or empty in the structured layer.
- `due` can only be filled when the transcript states a time explicitly.
- For topics without a clear conclusion, mark them as no-conclusion in the structured layer and avoid consensus language.
- If evidence lookup fails, drop the generated item instead of keeping a weak or unsupported statement.

## Output Shape

- Internally, prefer a structured JSON representation first.
- User-facing output should be rendered from the structured layer into the meeting-type template.
- Keep the structured layer and rendered layer aligned. Do not maintain separate business logic for each unless there is a strong reason.
- Preserve the ability to click or map rendered items back to transcript evidence.

## Implementation Guidance

- Prefer a fixed pipeline over agentic orchestration.
- Keep model usage narrow and observable:
  - classification
  - topic segmentation
  - per-topic extraction
  - final summary/render assist if needed
- Keep validation and verification in code, not prompt instructions alone.
- Prefer small, composable modules over large orchestration files.
- Avoid adding one-off helpers that are only used once unless they clearly improve readability.
- Reuse existing abstractions before introducing new layers or indirection.

## Change Size And Staging

- Aim to minimize the footprint of each change.
- For non-mechanical changes, prefer small reviewable stages over large rewrites.
- If a change starts to mix product rules, pipeline logic, rendering, and evaluation updates at once, split it into smaller stages when possible.
- Do not expand scope from MVP pipeline work into collaboration systems, task-system integration, or permissions features unless explicitly requested.

## Testing And Verification

- New logic that changes extraction, classification, verification, or rendering behavior should include tests or fixtures that cover the behavior.
- Prefer dataset-driven or integration-style checks for pipeline behavior over brittle micro-tests.
- Add or update fixtures when changing:
  - meeting classification
  - template selection
  - evidence verification
  - owner assignment
  - due-date extraction
  - no-conclusion fallback
- If a user-visible output format changes intentionally, update the corresponding examples or fixtures in the same change.
- Never silently truncate over-limit transcripts. Inputs above product limits must fail explicitly.

## Prompt And Template Rules

- Prompts must be template-aware and meeting-type-aware.
- Prompts must not ask the model to infer facts that the verifier would reject.
- Keep prompt files focused by stage, for example:
  - classification
  - segmentation
  - extraction by meeting type
  - summarization
  - JSON repair
- Do not hide product policy in a single giant prompt when the same rule can be enforced in code.

## Data And Privacy

- Use constructed or approved sample transcripts for local development and evaluation.
- Do not introduce real meeting data into the repository unless explicitly approved.

## Repository Conventions

- Put durable product specs and technical plans in `docs/`.
- Put pipeline code in `src/`.
- Put prompts in `prompts/`.
- Put sample datasets and judges in `evals/`.
- Put user-facing local rendering assets in `web/`.

## What To Avoid

- Do not turn this project into a generic chat UI.
- Do not optimize for fluent prose at the expense of evidence and correctness.
- Do not treat brainstorming or unresolved discussions as finalized decisions.
- Do not bypass verification just because a model output looks plausible.
- Do not introduce broad framework complexity when a direct pipeline step is enough.

## Source Note

- This file is adapted for this repository from the style and intent of OpenAI Codex repository guidance, not copied literally.
- The upstream file used as reference is:
  `https://github.com/openai/codex/blob/main/AGENTS.md`
