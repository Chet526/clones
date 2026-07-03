---
name: forensic-law-enforcement-data
description: 'Use when analyzing tower dumps, CDR/CSLI, geofence returns, GPS traces, app location exports, call/text metadata, and cross-source timelines for law-enforcement investigations. Trigger words: tower dump, phone records, CDR, CSLI, sector azimuth, dump analysis, triangulation, confidence scoring, chain of custody.'
argument-hint: 'Case objective, source record types, time window, timezone, and jurisdictions'
user-invocable: true
---

# Forensic Law-Enforcement Data Analysis

## Purpose
Convert mixed-source telecom and location evidence into clear, defensible investigative outputs for detectives, analysts, and prosecutors.

## When To Use
- Tower dumps and CDR/CSLI interpretation
- Geofence and app location timeline reconstruction
- Multi-source corroboration (carrier + app + device + reports)
- Confidence scoring, anomaly flags, and court-facing summaries

## Workflow
1. Define scope: incident window, jurisdiction, legal constraints, and timezone policy.
2. Inventory sources: identify each file type, provider, and known data-quality caveats.
3. Normalize timestamps and coordinates; document every assumption.
4. Build event timeline with explicit source attribution per event.
5. Score confidence for each key inference (high, medium, low).
6. Identify contradictions, missing intervals, and alternate explanations.
7. Produce an investigator summary plus an exhibit-ready evidence table.

## Required Output Sections
- Source inventory (origin, hash, period covered)
- Data quality findings (gaps, duplicates, drift, uncertain timezone)
- Timeline narrative with source references
- Confidence matrix for major conclusions
- Chain-of-custody and verification checklist

## Guardrails
- Never state legal conclusions (guilt/probable cause) as facts.
- Preserve source truth; do not alter original evidence content.
- Separate observed facts from inferred interpretations.
- Always include caveats for low-confidence inferences.

## References
- [Record Type Playbook](./references/record-types.md)
- [Evidence Narrative Template](./references/evidence-narrative-template.md)
