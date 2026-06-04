# Changelog

All notable changes to deep-sota will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-06-04

### Added
- Skill now ingests ACL Anthology papers (bare id, landing URL, or
  `.pdf`/`.xml`/`.bib` asset URL) through the same
  `mcp__lodestone__ingest_paper` tool that handles arxiv. Requires
  lodestone ≥ 0.2.0.
