# Public package audit and provenance notes

## 2026-10-26 English-to-Chinese evidence addition

The new translation package contains the same licensed public inputs, raw OCR and translation JSON, local model request/response evidence, unmodified DOCX outputs, and actual LibreOffice PDF/PNG renders. Only the private working-tree path inventory is omitted from public execution metadata; this is marked explicitly. Original records remain in the local experiment directory. Same-model baseline and final OCR/translation content projections match.

The complete renderer, local HTTP model adapter, execution scripts, private pickles, downloaded dependencies and model weights are excluded. The eight algorithm examples and earlier artifact hashes remain unchanged. Loopback addresses and container paths in evidence describe the isolated run, not a private deployment endpoint. The new publishing entries are individually enumerated; this addition does not authorize exporting the parent repository.

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

## 2026-10-26 public-source and local-run additions

The new PLOS source is the publisher's unchanged public PDF, with article attribution and CC BY 4.0 evidence in `CASE_SOURCES.md` and `samples/plos-best-practices-source.json`. Only page 2 is used as an OCR input. Its native text reference remains separate from OCR predictions and is not labelled human ground truth.

The published local-run JSON and DOCX files are byte-identical copies of the outputs produced by the private project in the isolated CPU containers. No text or document layout was corrected for presentation. Each DOCX was rendered separately and every resulting page was visually inspected; both failed the visual review. All failed outputs are retained with their observations.

The public execution records retain dependency versions, settings, actual model hashes, source revision and selected executed-source hashes. They omit the private working-tree inventory of unrelated modified files. The full raw private record is identified by SHA-256, not copied into the public package. Container-local paths such as `/work/inputs` and `/app/model_zoo` are reproducible runtime paths, not private host locations. Full runtime logs, the verification runner, model files, temporary renderer images and local environment configuration are excluded.

Common credential, private IP and host-path patterns were checked across public text files and the new DOCX XML. Three host-path-shaped matches were reviewed: two are intentionally invalid paths in security tests, and one is the generic Windows Arial font location. No actual private host path, credential or server address requiring redaction was found. Both new DOCX creators are the generic `python-docx`; neither contains an external relationship. Their template metadata dates are left unchanged and are not used as run dates. New rendered PDF metadata contains the generic creator and LibreOffice producer, and new PNG metadata only records DPI.

The original eight business snippets and all frozen historical input/output evidence remain unchanged. New integrity-check tooling follows the existing verification-tool scope; no additional business implementation is published. Checks establish the reviewed scope, not a guarantee against every possible secret format or an independent human quality certification.

## 2026-10-26 DOCX export repair evidence

The new `artifacts/local-docx-fix-20261026/` directory contains a fresh pipeline run after changes to the private exporter. Its JSON and DOCX are byte-identical to that run's outputs; previews were rendered from those DOCX files without manual edits. Renderer-side font fitting, source-ink masking on verified flat backgrounds and image layering are recorded engineering changes, not retouching of the published previews. Inputs, OCR predictions and the original failure directory remain unchanged.

The same privacy scan was repeated across 106 public text files and the new DOCX XML, PDF metadata and PNG metadata. The three host-path-shaped matches remain synthetic security-test inputs and the generic Windows font path; no credential or private host address requiring removal was detected. Binary creators remain generic, with no external DOCX relationships. The execution-record copies omit the private worktree inventory and identify the full private records by hash. Failed intermediate development probes and their logs remain private.

The explicit publication allowlist adds only the new case documentation and reviewed outputs/audits. The complete exporter and its new regression tests are outside `showcase/`; all eight public business algorithms retain their earlier hashes. Target-specific visual acceptance does not extend the license or imply a full-document fidelity guarantee.

## 2026-10-27 faithful Chinese layout evidence

The two new cases were rerun from an immutable private source snapshot with OCR, real English-to-Chinese model requests, the existing faithful exporter, and independent LibreOffice rendering. Published OCR JSON, translated JSON, model responses, DOCX, PDF and PNG are unchanged copies of those outputs. The saved full audit is supplemented with a separately identified visual review; automatic violations were not removed or waived. Historical single-column and failed outputs remain unchanged.

The scan covered 145 public text files and both new DOCX XML packages, PDF metadata and PNG metadata. The four host-path-pattern file hits refer to the already documented public government `/home/Download/` endpoint and its explanation; they are not private filesystem paths. No credential or private-IP pattern was found. New DOCX files have generic python-docx metadata and no external relationships; PDFs have generic Writer/LibreOffice metadata, and PNGs only carry DPI. This is a bounded pattern/content review, not a guarantee against every possible secret format.

Only the private working-tree inventory is omitted from public execution-record copies; the original raw record is retained locally and identified by SHA-256. Container-local runtime paths remain. The font provenance and SIL OFL texts accompany embedded Noto subsets. Full fonts, model weights, backend adapters, execution scripts, source snapshots, runtime logs and business fixes remain outside the public package. The original eight selected business algorithms and 122 previously frozen sample/evidence/example files retain their hashes.

## 2026-10-27 comparison heading removal

The new `artifacts/table-display-20261027/` copies remove only the requested top headings and descriptions from the English PDF text stream and the Chinese DOCX paragraph objects. Both previews are direct new renders; table/footer pixels match each respective baseline outside the removed heading area. The Word table XML is byte-identical. Original inputs, old artifacts and all public/private application code remain unchanged. New records use public relative paths and artifact hashes; no private helpers or source snapshots are included.

## 2026-10-27 native Word table artifacts

The separate `artifacts/native-table-20261027/` directory contains one native Word table reconstructed through an existing application helper from the saved predicted cells and spans. It removes the old background image and table-area frames; two quantities are transcribed from the visible public source into native cells and explicitly marked as document edits, not OCR output. The final DOCX contains no image parts or external relationships. The source truth is used only for acceptance. Original application/public Python code and all 192 earlier sample/evidence/example/Python files retain their hashes; no private implementation or temporary utility is included.

The final DOCX, PDF and PNG are unchanged copies of the second isolated rendering round. Public JSON copies normalize source paths to the public root, identify the unpublished first diagnostic by hash and update the linked record hashes accordingly; measured results are unchanged, and raw record hashes are retained. A scan of 170 public text files plus the new document XML/relationships and PDF/PNG metadata found no credential or private-IP pattern. Four pre-existing path-pattern file matches remain the documented public government download URL and explanations. Document metadata is generic python-docx/Writer/LibreOffice, with DPI-only PNG metadata. Native structure, complete cell text and visual acceptance are separately recorded; Microsoft Word interactive editing was not tested.

## 2026-10-27 table status translation artifacts

The separate `artifacts/status-translation-20261027/` directory adds four assistant-written Chinese status labels to the saved table document. It reuses existing source-glyph removal, native frame and font embedding helpers; no application or public Python code changes are included. Original source strings, OCR/model responses, the earlier DOCX and all 181 frozen sample/evidence/example/Python files retain their hashes. The source mask is local to the four status glyph regions; pixels outside it are unchanged. Final PDF and PNG are direct renders of the new DOCX, without preview retouching.

The scan covered 163 public text files plus the new DOCX XML/relationships and PDF/PNG metadata. No credential or private-IP pattern was found. Four existing path-pattern file matches are the previously documented public government download URL and its explanations. The DOCX uses generic template metadata and no external relationships; the PDF has generic Writer/LibreOffice metadata, and the PNG only carries DPI. The new public run record selects execution parameters and artifact hashes from the private run, identified by hash; temporary scripts, pickles, source snapshots, full fonts and logs remain private. Semantic coverage is separately reviewed across every source table cell and outside text region; the original audit's literal-preservation counters are not relabelled as translation completeness.

## 2026-10-27 reviewed translation artifacts

The separate `artifacts/reviewed-translation-20261027/` directory contains user-requested assistant post-edits, not new model outputs. Before/after text and visible-source symbol/count corrections are explicit in `corrections.json`. The original OCR, model responses and all earlier artifact bytes are retained. The table DOCX alone receives one explicit footer line break after export; final previews and audits were regenerated from that exact file.

The application source snapshot (460 files), all 27 public Python files, and the original eight snippets remain unchanged. New private artifact utility scripts are not published. New DOCX XML and relationships plus the nine local JSON records were checked for host paths, local usernames, hostnames and common credential formats; none were found. `/inputs` and `/work/audits` are container paths. Both DOCX packages have valid ZIP CRCs, generic template metadata and no external relationships; embedded PNGs have no EXIF/text metadata. Template creation dates are not used as run dates. PDF/PNG metadata and final publication checks are recorded in the validation update.
