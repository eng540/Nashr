# ADR-013: Versioned Output Contract Control Plane

- **Status:** Accepted for implementation
- **Date:** 2026-10-10
- **Scope:** Production Platform Foundation — Output Contract
- **Depends on:** ADR-011 Recipe Control Plane and ADR-012 Editorial Identity

## Decision

An Output Contract is a versioned, provider-neutral definition of the shape and storage form of an Artifact. It is separate from editorial Identity, Policy, Prompt Template, Recipe, and the provider implementation.

The initial definition records artifact kind, MIME type, content mode (INLINE or STORAGE_URI), required metadata fields, and an optional maximum inline-content length. Validation rejects unsupported artifact kinds, mismatched MIME types, invalid storage modes, duplicate metadata requirements, invalid lengths, and unknown fields.

## Lifecycle

Output contracts have stable keys and immutable published versions. New contracts begin with DRAFT v1. Only DRAFT versions can be edited or published. Publishing a replacement archives the previous PUBLISHED version. PostgreSQL enforces at most one PUBLISHED version per contract.

Migration 0021 seeds TELEGRAM_POST v1 to describe the existing inline Post output. This seed is a data contract, not a claim that arbitrary IMAGE/VIDEO production capabilities already exist.

## Runtime boundary

This stage establishes the durable contract catalog and lifecycle API. ProductionJob resolution/pinning, artifact validation against a pinned contract, and persistence of the contract key/version are a separate required runtime integration gate. Until that integration is merged and tested, contracts created through this API do not change generated output.
