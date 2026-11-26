# ai-test-harness

An AI-powered test harness built with **LangGraph** and **Playwright** (Python).
LLM agents plan, execute, validate and analyze end-to-end tests derived from
acceptance criteria.

System under test: [www.lu2met.ar](https://www.lu2met.ar) — the author's amateur radio website (LU2MET).

> 🚧 Work in progress.

---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	planner(planner)
	executor(executor)
	evaluator(evaluator)
	__end__([<p>__end__</p>]):::last
	__start__ --> planner;
	evaluator -.-> __end__;
	evaluator -.-> planner;
	executor --> evaluator;
	planner --> executor;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc

