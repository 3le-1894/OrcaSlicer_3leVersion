# Prepared native regression fixtures — UNEXECUTED

No compilation or native execution occurred. Both standalone C++ fixtures require assertions enabled in a later approved build. `prepare.py` extracts the actual candidate callback/methods and queue/registration blocks; `SNIPPETS.json` pins those source snippets. They are source-extraction fixtures with synthetic GUI/capability/app/logger substitutes, not full wx/WebKit qualification.

- `page_readiness.cpp`: actual content gate, bootstrap handler, detach method and constructor completion lambda. Checks bootstrap-first, handler-first, repeated success/bootstrap, failed registration, disable before completion, callback after destruction and old callback versus a new enabled page.
- `registration.cpp`: actual per-target weak-reference/callback queue and completion scheduling code. Checks two distinct callbacks, ordinary callback-free drainer, delayed/reentrant enqueue/drain, failure, already-added registration and a target destroyed while queued. Synthetic weak tracking models invalidation but does not exercise wxWeakRef itself.

Future native/platform qualification must additionally test real wxWeakRef destruction and event cancellation, Windows synchronous registration with deferred completion, macOS deferred registration/duplicate guard, Linux injection ordering, fake-view failure, and page removal/shutdown during pending work. Assertions and fixture extraction hashes must be checked before execution. No build commands are executed by the preparation helpers.
