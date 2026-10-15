# Public package audit and provenance notes

Audit date: 2026-10-15. Scope: this selected `showcase/` package, including readable source, documentation and JSON evidence, and document/image metadata. This is not an audit or release of the complete private project.

## Privacy checks

The inspected text and metadata contained no confirmed login credentials, private keys, credential-bearing URLs, private server connection addresses, or private absolute filesystem paths that required removal. Checks covered common secret fields and token patterns, SSH/server addresses, local filesystem paths, DOCX core properties and relationships, PDF document metadata, and PNG text metadata. This statement describes the checks performed; it is not a claim that every possible secret format or information visible in image pixels was manually reviewed.

Public source URLs remain intact for reproducibility. In particular, the government download URL containing `/home/Download/` is a public web endpoint, not a private home-directory path. Its occurrences in source metadata and source documentation were retained.

The generated DOCX and rendered PDF metadata did not reveal a personal author or private host path. The upstream `samples/c03-source.pdf` has an empty Author field; its existing Creator field is retained as upstream metadata and does not contain a detected private path or email pattern. No claim is made about the identity represented by that field. PNG files inspected contained no textual metadata. Original binary sample files were not rewritten or deleted.

## Provenance corrections

`CODE_PROVENANCE.json` now explicitly describes all eight examples as **historical selected snapshots**, not the complete or latest implementation of the private service. Every existing `source_sha256` is preserved as the source-module identity recorded when the snippet was extracted. Later changes in the private source do not change that historical identity.

The `example_sha256` values for `examples/literal_guard.py` and `examples/engineering_metrics.py` were recalculated from the exact bytes in this public package. The previous recorded values are retained under `previous_recorded_example_sha256`. The audit did not modify either example's code. All eight packaged example hashes were verified after this correction.

No report measurements, evaluation outcomes, model names, weight identities, algorithm content, or original source/download hashes were changed by this audit. No artifact JSON required redaction.

## Publication and dependency boundary

The eight example modules contain 753 lines in total and expose selected functions and small supporting types. They do not import the private parent application's packages. One example imports another module within `examples/`; the PDF probe has an optional `fitz` (PyMuPDF) dependency. The public package's sample-preparation dependencies are separate from the private OCR service and model runtimes.

Original selected code follows `CODE_LICENSE.txt` and the scope described in `LICENSE.md`. Public third-party drawing samples retain their source and license information, including `samples/DEXPI-LICENSE.txt`. Optional libraries, upstream assets, model weights, and the unreleased service retain their respective license terms; their inclusion or mention does not extend the selected code's license to them.

Publish only the reviewed package files recorded by the final publication allowlist. Do not publish the parent project or its Git history, local environments, caches, model weights, runtime/host configuration, credentials, personal documents, or unreviewed source data. Publication tooling should regenerate and verify its file manifest after this audit and other package edits are complete.
