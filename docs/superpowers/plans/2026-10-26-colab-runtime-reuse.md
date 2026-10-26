# Colab runtime reuse and separate readiness probe

Scope: preserve the original packet and every model/downloader/meta/worker/guard byte, revision, once marker, 600-second freshness limit, 1,800-second download deadline and memory guard policy. No Colab execution, dependency installation or download is part of this change.

1. Add synthetic regression cases for repeated preparation, incomplete/tampered preparation, separately gated full preflight, failed/expired freshness, original proof preservation and default Run all without IO.
2. Split the reviewed setup cell immediately before its original full preflight. Successful installation records a prepared context. Repeated preparation validates that context, public source bytes and exact installed metadata, then skips all installation. Failed/incomplete preparation stops on the next click without creating a new ROOT.
3. Run the unchanged full preflight payload only through a separate default-off gate. Use a fresh UUID subdirectory for proof/output. A failed probe clears freshness while preserving a valid prepared runtime. No lightweight memory check replaces the original GPU/metamodel/namespace checks.
4. Generate a distinctly named notebook in a new private evidence directory, compare embedded payload hashes to the original, run targeted offline tests with external network denied, and document unverified GPU/RAM effects and the existing quota restriction.
