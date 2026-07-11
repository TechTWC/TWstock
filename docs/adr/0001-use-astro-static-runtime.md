# ADR 0001: Use Astro Static Runtime

## Status

Accepted

## Context

TWStock currently has research governance documentation but no runnable website
project. Issue #9 establishes the first minimal local website scaffold while
keeping investment strategy, registry, backtesting, authentication, API, and
deployment concerns out of scope.

The project needs a reproducible local runtime so future website work starts
from the same Node.js and package-manager versions.

## Decision

Use Astro with static output for the initial TWStock Research Console scaffold.
The local runtime is pinned to Node.js `24.18.0`, and the package manager is
pinned to pnpm `11.11.0`.

The scaffold uses:

- Astro static output via `output: "static"`
- TypeScript strict configuration via Astro's strict preset
- `pnpm-lock.yaml` for dependency resolution
- A minimal static homepage at `src/pages/index.astro`
- No server adapter and no SSR

## Alternatives considered

- Plain static HTML: simpler, but does not establish the intended Astro project
  structure or TypeScript checking path.
- Vite-only site: viable for static output, but less aligned with a content-first
  research console and future static pages.
- Next.js or another React framework: unnecessary for the approved minimal static
  homepage and would introduce React without a concrete need.

## Consequences

- The project can run local development, typechecking, production builds, and
  static previews with pnpm scripts.
- Static output is generated in `dist/`.
- Future interactive or multi-page website work can build on Astro without
  committing to SSR, adapters, APIs, or database infrastructure now.
- Runtime drift is reduced by pinning Node.js and pnpm exact versions.

## Explicit non-goals

This decision does not add:

- React
- SSR
- Astro adapters
- Cloudflare Worker or deployment configuration
- GitHub Actions
- API routes or server endpoints
- Database access
- Login or authentication
- Registry schema or sample seed data
- Dashboard, strategy, experiment, decision, or validation pages
- Backtest engine, market data, analytics, or investment strategy rules

## Rollback condition

If the scaffold blocks repository governance work, proves incompatible with the
approved static-only direction, or is superseded by a later approved website
architecture decision, revert the scaffold commit and replace this ADR with a new
accepted decision.
