# Waypoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend-first MVP described in `waypoint_codex_build_prompt.md`.

**Architecture:** FastAPI routes delegate to service modules. Parser adapters produce canonical
Pydantic objects. Pure normalization and crime-summary functions stay independent of the
database, while SQLAlchemy models and Alembic migrations provide persistence.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, pytest, Docker Compose,
PostgreSQL/PostGIS.

---

## Implemented Tasks

- [x] Add parser, normalization, crime, export, and API tests.
- [x] Implement Google Timeline, CSV, GeoJSON, and GPX adapters.
- [x] Implement haversine distance, stop detection, recurring-place clustering, and sensitive
  location inference.
- [x] Implement Seattle crime fixture ingestion and pure radius summaries.
- [x] Implement SQLAlchemy models and API services.
- [x] Implement import, normalize, places, crime, and Tableau export endpoints.
- [x] Add Alembic migration, Docker Compose, Makefile, `.env.example`, and README.

## Remaining Follow-Ups

- [ ] Harden Google parser against additional real on-device Timeline exports.
- [ ] Add live Socrata ingestion endpoint with pagination controls.
- [ ] Add production authentication, encryption at rest, and tenant isolation.
- [ ] Add route/trip extraction as a V2 slice.
