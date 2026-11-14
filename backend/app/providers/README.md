# Providers

## Overview
External provider integration layer organizing LLM provider transports and adapters.

## Interface
- [LLM](./llm/README.md): LLM provider interface and adapters for local OpenAI-compatible endpoints and hosted OpenRouter

## Invariants
- Hosted providers remain strictly disabled and fail-closed until explicitly configured and allowed by operator [llm/openrouter.py]

## Side Effects
- Outbound network requests to local or remote LLM chat completion endpoints when reranking candidates [llm/]

## Verification
- Run: `pytest backend/tests`
