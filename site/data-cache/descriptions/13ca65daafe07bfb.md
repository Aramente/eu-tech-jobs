### Job Summary:

In this position, you will build and scale the backend for a borderless neobank on stablecoin rails. You’ll work across traditional banking integrations, blockchain infrastructure, and card issuance - ensuring every transaction is correct, every webhook is idempotent, and every workflow survives a crash. We are an agentic-first engineering team: you’ll ship with AI-assisted tooling daily, not as an experiment.

This is a remote position. We do not offer visa sponsorship or assistance. Resumes and communication must be submitted in English.

### Responsibilities:

*The following information is intended to describe the general nature and level of work being performed. It is not intended to be an exhaustive list of all duties, responsibilities, or required skills.*

**What You’ll Own**

* End-to-end feature delivery across banking, cards, crypto, and compliance modules
* Temporal workflow design for critical financial operations
* Webhook integration reliability (inbox pattern, signature verification, IP whitelisting)
* Event-driven architecture evolution
* Observability and incident response for payment flows

**Our Way of Work**

* Agentic-first: AI tools are infrastructure, not novelty. You’ll use Claude Code with custom skills, automated reviews, and MCP integrations daily
* Correctness over speed: This is a financial system — idempotency, transactional integrity, and crash-resilience are table stakes
* Codified standards: Architecture decisions live in .claude/rules/, ADRs, and per-module CLAUDE.md files — not tribal knowledge
* TDD encouraged: Red-Green-Refactor with dedicated tooling support
* Pre-commit quality gates: Lint + typecheck on commit, full test suite on push

### Qualifications and Job Requirements:

**Core Backend**

* Strong TypeScript/Node.js (NestJS preferred)
* PostgreSQL — schema design, transactions, advisory locks, performance tuning
* GraphQL API design (Apollo Server, resolvers, custom scalars, pagination)
* Event-driven architecture — outbox/inbox patterns, idempotency, at-least-once delivery

**Distributed Systems & Reliability**

* Temporal.io or equivalent durable workflow engine (Cadence, Step Functions)
* Designing idempotent activities and deterministic workflows
* Retry policies, non-retryable error classification, and failure handling
* Transaction boundaries in distributed systems

**Fintech Domain**

* Payment rails familiarity (ACH, SWIFT, Fedwire) or willingness to learn quickly
* Double-entry accounting concepts
* Webhook signature verification (HMAC, ECDSA, Svix)
* KYC/KYB compliance flows

**Web3 / Blockchain**

* Solana ecosystem (SPL tokens, transaction construction, RPC interaction)
* Stablecoin mechanics (USDC, EURC, mint/transfer/burn)
* Wallet custody models (MPC wallets via Privy or similar)
* Cryptographic signing (KMS-backed ECDSA)

**Agentic Engineering**

* Proficiency using AI coding assistants (Claude Code, Cursor, Copilot) as a daily multiplier
* Ability to write effective prompts, review AI-generated code critically, and maintain code quality
* Comfort with AI-assisted workflows: automated PR reviews, test generation, codebase exploration
* Understanding when to trust AI output and when to verify manually

**Observability & Operations**

* APM and tracing (Datadog or equivalent)
* Error tracking (Sentry)
* Structured logging (Pino/Winston)
* Blue-green deployments, health checks, graceful shutdown

**Nice to Have**

* Experience with Privy, Sumsub, Noah, or Rain APIs specifically
* AWS KMS / HSM-backed signing
* PostgreSQL logical replication
* NestJS module architecture at scale (20+ modules)
* Contributing to internal developer tooling (custom slash commands, MCP servers, Claude Code hooks)