BUILD RAG CODEBASE INDEX
========================

Creates codebase_vectors.json in the Hermes project root for hermes_orchestrator RAG search.

PREREQUISITE
------------
  scripts\install_models\03_install_python_packages.bat   (sentence-transformers / bge-m3)

RUN ORDER
---------
  01_build_index.bat              Incremental index (only changed files)
  02_build_index_full.bat         Full rebuild (re-embed everything)
  03_verify_index.bat             Check index exists and has chunks
  04_verify_incremental_growth.bat  Test add/reuse/remove cycle

WHEN TO RUN
-----------
  - First time before running hermes_orchestrator.py
  - After significant code changes (or let trigger_codebase_reindex handle it during runs)

INDEX SCOPE (default)
---------------------
  By default indexes THIS project only (Hermes_Orchestration) — fast incremental runs.
  To index more folders, set before running:
    set HERMES_WORKSPACE_ROOTS=C:\path\one;C:\path\two

  Previously the fallback was the entire Desktop (400+ files) — that caused very slow builds.

INCREMENTAL BEHAVIOR
--------------------
  - New/changed files: re-embedded
  - Unchanged files: reused from existing index (fast)
  - Deleted files: removed from index

OUTPUT
------
  Hermes_Orchestration\codebase_vectors.json
