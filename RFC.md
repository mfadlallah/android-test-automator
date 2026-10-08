# Hybrid AI Mobile Regression Agent — Updated RFC

**RFC · Proof of Concept · Mohamed Fadl Allah · 7 October 2026**

**Repository:** https://github.com/mfadlallah/android-test-automator

---

## Problem and objective

The friction in this workflow is well known. Today, an engineer creates a TestRail run, reads each test case, executes it manually on the app, and then returns to TestRail to record the result—including every passed test. This repetitive device interaction and manual result entry make regression testing tedious and consume valuable engineering time.

Test cases may also be duplicated or adapted across platform-specific automation suites, creating additional maintenance effort and a risk of Android, iOS, and TestRail definitions drifting apart.

The objective is to eliminate this friction for supported journeys by automating execution, evidence capture, and eventually TestRail result reporting. TestRail will remain the single source of truth for test intent, execution status, and regression history. The agent will consume the same human-readable test case and execute it through appropriate platform adapters, allowing engineers to focus on failures, uncertain outcomes, and test intent instead of routine checks and manual pass recording.

---

## Proposal

Use a hybrid agent: a local AI model translates human-readable test cases into a validated capability plan, while deterministic Python executors perform grounded actions and evaluate structured evidence. AI also assists with visual ambiguity. The model never sends commands directly to the device; when hierarchy and OCR evidence are inconclusive, it may provide a bounded visual assessment that must pass deterministic evidence checks.

QA engineers and contributors can create or update test cases centrally in TestRail using product intent and visible UI labels, without needing knowledge of Android or iOS application code, ADB, XCUITest, OCR, or Python. The same test intent can be executed across supported platforms through platform-specific adapters.

The automation repository contains reusable capabilities, grounding logic, recovery policies, and domain-agnostic adapters—not independent copies of the test-case source. Code changes are required only when a case introduces a genuinely new interaction pattern or an unsupported UI structure. Domain-specific code has been eliminated in favor of semantic, generic approaches.

During the PoC, local plain-text case files act as the input contract. In the next phase, the agent will retrieve cases directly from TestRail and upload results and evidence back to the corresponding TestRail run. This is a PoC and is not yet a replacement for release-critical regression.

---

## Current implementation

**PoC coverage:** Three implemented test cases across layout transitions and complex sorting. Two verify layout transitions (card-to-row and row-to-card). The third is a more complex sorting journey covering optional-modal recovery, filter selection, state verification, scoped positive and negative assertions, asynchronous list refresh, and scrolling. This exercises multiple agent capabilities within one end-to-end flow.

**Generic domain-agnostic adapter:** The PoC now uses a completely generic test execution system with no domain-specific code. The `GenericAdapter` uses:
- **Semantic heading detection** via OCR with intelligent filtering (position threshold ≥500px, width <50%, excludes banners/controls/search)
- **Material Design layout positioning** for two-option controls (right-aligned toggles, vertically aligned with detected heading)
- **Multi-tool visual evidence capture** with fallback chain: PIL → ImageMagick → ffmpeg → JSON metadata
- **Region-aware observation filtering** for stability and recovery detection
- **Toggle position caching** from hierarchy when available
- **Observation caching** to reduce redundant OCR/hierarchy calls

This approach works for any heading + any two-option control (RadioButton/RadioGroup, Toggle, SegmentedControl) across any app with no hardcoded resource IDs or domain-specific adapters.

**Generic interruption recovery:** The PoC can detect and dismiss unexpected dimmed sheets or Braze popups that are not declared in the test steps. It verifies that the interruption is closed and resumes the same pending step without advancing the plan or navigating away from the intended flow.

**Scope:** Android; card-to-row, row-to-card, and sorting by Ratings (High To Low) in Vendor Discovery domain. All test cases use the same generic adapter without domain-specific code.

**Host:** macOS; ADB/UIAutomator, Apple Vision OCR, and multi-tool image cropping.

**AI:** Local Ollama; default `qwen2.5vl:3b`. Loopback endpoint and cloud-inference restrictions.

**Planning:** AI normalization, schema validation, up to three planning attempts, then controlled-language fallback.

**Execution:** Sequential capability runner using generic adapter for all layout control operations. No domain-specific adapters or hardcoded patterns per domain.

**Results:** PASSED, FAILED, or BLOCKED; later-attempt success remains PASSED with `flaky: true`.

**Suite:** `run_all_tests.sh` executes cases sequentially, continues after failures, and groups artifacts by case and attempt. Current per-case timeout: 30 minutes.

**Boundary:** iOS, CI orchestration, TestRail/Jira/Slack integrations, and unrestricted cross-domain execution are planned work. Existing unit/integration automation remains complementary.

---

## Architecture and AI responsibilities

| Component / source | Responsibility and AI boundary |
|---|---|
| **Planner** — `src/planning.py` | AI interprets wording, synonyms, and minor typos. Validation checks roles, values, supported capabilities, and normalizes plans. Controlled fallback accepts recognized numbered steps. |
| **Capability registry** — `src/capabilities.py` | Defines the shared contract between language planning and execution: 12 capabilities with required fields and valid roles. |
| **Observer / grounding** — `src/main.py` | Captures PNG, XML, and nodes. Resolves labels/descriptions via hierarchy, OCR, or semantic heading detection. Constrained vision assists when needed. |
| **Generic adapter** — `src/adapters/generic_adapter.py` | Universal domain-agnostic layout control grounding using semantic keyword matching, OCR-based heading detection, and Material Design positioning patterns. No hardcoded resource IDs. |
| **Executor** — `src/main.py` | Sends validated ADB actions. Layout transitions use generic adapter; other supported plans run step by step. |
| **Recovery** — `src/recovery.py` + `src/main.py` | Detects optional modals using hierarchy, OCR, SDK markers, geometry, or dimming; protects planned sheets and verifies closure. Includes delivery-address, offer, and Braze adapters. Detects prior successful recovery to tolerate transient states. |
| **Assertions / evidence** — `src/main.py` | Uses scoped hierarchy/OCR, enlarged crops, and visual assessment. Relevance and polarity checks constrain model verdicts. |
| **Retry / suite** — `src/main.py` + `run_all_tests.sh` | Preserves per-attempt evidence, reruns unsuccessful cases, and produces case and suite summaries. |

**12 capabilities:** `tap`, `recover_optional`, `set_control`, `scroll`, `assert_scrolled`, `assert_changed`, `assert_visible`, `assert_hidden`, `assert_contains`, `assert_not_contains`, `assert_selected`, `wait_changed`.

---

## Generic layout control grounding

The system detects layout controls generically without domain-specific code or hardcoded resource IDs:

**Heading detection** (OCR with filtering):
- Confidence ≥0.7, text length >2, height ≥30px
- Y-position ≥500px (excludes status bar)
- Width <50% of screen (excludes full-width controls)
- Excludes banners (`offer`, `hour`, `discount`, `deal`, `expires`, etc.)
- Excludes action buttons (`+`, `-`, `|` prefixes)
- Excludes search bars

**Scrollable container detection** (ADB hierarchy metadata):
- Checks for `scrollable` flag on nodes
- Detects RecyclerView, ListView, ScrollView, ViewPager by resource ID and class name
- Trusts ADB hierarchy structure over size-based heuristics

**Item detection within containers** (Hierarchy parent relationships):
- First identifies container node by matching bounds
- Uses parent-child relationships to find direct children (potential list items)
- Falls back to bounds-based search only if hierarchy approach fails
- Selects topmost item as first visible

**Toggle positioning** (Material Design right-alignment):
- Detects RadioButton/RadioGroup/ToggleButton/SegmentedControl from hierarchy
- Right-aligned: 100–180px from right edge
- Vertically aligned with detected heading center
- Positions cached from hierarchy when available; computed dynamically otherwise

**Visual evidence capture:**
- Primary: PIL (Python Imaging Library)
- Fallback 1: ImageMagick `convert` command
- Fallback 2: ffmpeg
- Fallback 3: JSON metadata + full screenshot
- Ensures evidence is captured in all environments

**Observation caching:** Reduces redundant OCR and hierarchy queries during recovery and assertion paths.

---

## Authoring, execution, and evidence

An illustrative case uses explicit targets and expected values. Prefer actual visible wording; resource-ID hints help when labels are unavailable.

**Title:** Verify rating sorting removes advertised vendors.

1. Tap Restaurants on Home.
2. Recover safely from any optional foreground sheet.
3. Verify the first restaurant item contains "Ad".
4. Tap Filters.
5. Tap Ratings (High To Low).
6. Verify Ratings (High To Low) is selected.
7. Tap Apply.
8. Verify the Filters pill contains "1".
9. Verify the Filters sheet is closed.
10. Wait until restaurant items change and finish loading.
11. Verify the first restaurant item does not contain "Ad".
12. Scroll the restaurant list and verify content moved.

The planner converts each step into a capability, target, value, role, and expected outcome. Plan-only mode permits review before device interaction. The registry is a stable execution contract, not a dictionary of individual test cases.

```bash
python3 -m src.main --case cases/33271749-sort-restaurants-list.txt --plan-only
python3 -m src.main --case cases/33271749-sort-restaurants-list.txt
bash run_all_tests.sh
```

---

## Recovery and observation

Unexpected sheets can interrupt any step. Recovery must distinguish them from intentionally opened UI such as Filters, dismiss a grounded modal, verify closure, and resume the pending step. Back requires modal evidence; it must not become an automatic response to uncertainty.

The implementation has bounded hierarchy retries, post-action stability checks, screenshot/OCR fallback in selected paths, and detection of prior successful recovery to tolerate transient app states after recovery completes. Fallback broadens availability but does not establish that every screen or target is understood. Capture calls and model inference can still dominate latency; configured stability windows are not strict end-to-end deadlines.

---

## Assertion crops

Label assertions use scoped crops and size-dependent enlargement. A detected label gets a tighter crop; source bounds, crop images, metadata, and OCR are saved when that path executes. Deterministic shortcuts may complete a step without creating a crop.

Current first-item logic can choose a more fully visible item when the first is clipped. A missing label may trigger a top-right badge crop. These are implementation assumptions, not a generic proof that the original first item's entire content was inspected.

---

## Retries and reporting

A transient assertion may be re-observed up to three times; an unsuccessful case may run up to three attempts. Relaunch force-stops the app but retains app data and saved filters. Later success is reported as PASSED with `flaky: true`. The suite currently counts exit-code success as passed, including flaky success; adoption policy must inspect the retry metadata separately.

---

## Trade-offs and readiness gaps

| Decision / risk | Benefit | Trade-offs or required safeguard |
|---|---|---|
| **Generic domain-agnostic adapter** | Single adapter works across any app and any layout control; eliminates domain-specific code duplication; reduces maintenance burden; easier to extend to new domains. | Requires robust heading detection and Material Design pattern recognition; must handle edge cases (overlapping text, non-standard layouts, OCR misses). |
| **Semantic keyword matching over hardcoded IDs** | Works on any Android device/version without UIAutomator hierarchy availability; more generic and portable. | Requires OCR confidence and position filtering; sensitive to OCR accuracy and app-specific wording. |
| **Multi-tool visual evidence fallback** | Ensures evidence capture in all environments (local dev, CI, cloud runners). | Additional tool dependencies (ImageMagick, ffmpeg); fallback chains increase latency. |
| **Observation caching** | Reduces redundant OCR/hierarchy calls during recovery and assertions; improves overall latency. | Cached state may become stale; requires invalidation strategy for dynamic UI. |
| **Local AI** | Natural-language planning and local data handling. | Hardware-dependent latency, model context limits, and variable visual accuracy. |
| **Hybrid execution** | Reuses grounded actions and structured evidence; generic adapters reduce code. | More contracts to maintain; platform-specific assertions still required. |
| **Scoped zoom crops** | Improves recognition of small labels. | Incorrect scope or badge location can exclude evidence; preserve full source and crop metadata. |
| **Negative assertions** | Can confirm removal of a label. | Current crop path can pass absence after OCR misses or errors. Require grounded target coverage and usable evidence; uncertainty must not be treated as absence. |
| **Up to three attempts with flaky-result tracking** | Recovers from transient loading, hierarchy, OCR, or model failures while preserving evidence from every attempt. | Retries increase runtime and may inherit persisted application state. A recovered run is reported as PASSED with `flaky: true`, and required preconditions must be restored or verified between attempts. |
| **Conservative recovery** | Reduces accidental navigation. | Dimming alone is insufficient; correlate modal boundaries and controls and verify closure. |
| **Recovery tolerance after prior success** | Prevents false blocking after successful dismissal of transient modals. | Must track recovery success accurately; incorrect detection of prior dismissal may suppress real failures. |

---

## Evidence-gated rollout and adoption

### Staged rollout

| Stage | Scope and decision gate |
|---|---|
| **0 — Engineer-local Android** | Start with Vendor Discovery on engineers' machines. At least two engineers reproduce setup on agreed devices; record case, app, model, prompt, and runtime versions. Compare with manual results. Advisory only; no release gating or automatic ticket closure. |
| **0A — Bounded iOS spike** | After Android demonstrates reliability, validate two or three equivalent cases using an XCUITest/WebDriverAgent adapter. Start with Simulator, then a provisioned iPhone. Reuse planning contracts and artifact conventions; validate `accessibilityIdentifier`, coordinate mapping, and platform-specific modal dismissal. iOS has no generic Android Back. |
| **1 — Vendor Discovery CI shadow** | Run a representative regression subset alongside manual testing. Admit only validated platforms; Android CI need not wait for iOS. Review metrics before controlled adoption. |
| **2 — Shopping validation** | Expand after Vendor Discovery meets its gate. Measure capability reuse without scenario-specific patches; apply the same reliability criteria. |
| **3 — Other domains** | Expand incrementally by regression cost, business value, risk, and reuse potential. Each domain begins in shadow mode. |

### Pilot success criteria and ownership

The following figures are proposed placeholders. Before the pilot begins, QA should provide or approve the quality baseline and acceptance thresholds using historical manual-regression data. This includes the acceptable false-pass and flakiness rates, required manual-result agreement, evidence-completeness expectations, minimum sample size, critical-test classification, and supported device/build coverage. Engineering will confirm that these metrics can be measured consistently.

**Pilot exit criteria** (owned by QA and agreed with Engineering):
- Zero observed critical false passes
- At least 95% agreement with manually reviewed outcomes
- At least 95% actionable evidence completeness
- At most 5% flaky runs across four consecutive weekly cycles
- No unsafe or unexplained navigation

---

## Planned operational integrations

1. **TestRail:** Retrieve human-written test suites, consume approved cases/runs, publish results, and attach artifact links.
2. **Jira:** Update or automatically close weekly regression tickets only when the configured policy confirms all required cases and acceptable retry outcomes; unresolved failures, blocks, or flakiness keep tickets open.
3. **Slack:** Publish weekly summaries and actionable links to TestRail/Jira.

Updates must be idempotent, auditable, and manually overridable. Process exit code alone must not authorize regression-ticket closure.

---

## End-to-end evidence: complex sorting case

The following evidence comes from one captured execution of TestRail case 33271749. The plain-text case was compiled by the local AI planner into the capability plan, then executed against `com.hungerstation.android.web.debug` using `qwen2.5vl:3b` with the generic domain-agnostic adapter.

| Evidence field | Captured value |
|---|---|
| **Plan** | AI-generated in one planner attempt; normalization applied; no planner errors. |
| **Recovery** | Unexpected Hour Offer sheet detected, closed using OCR-grounded sheet geometry, and verified clear. |
| **Generic layout grounding** | Layout control (RadioGroup with RadioButtons) detected via hierarchy. Toggle position calculated using Material Design right-alignment pattern (y-aligned with heading). No domain-specific code. |
| **Result** | PASSED in attempt 1 of 3; `flaky: false`; terminal duration 327 seconds. |
| **Assertions** | Ad present before sorting; Ratings (High To Low) selected; Filters indicator equals 1; Ad absent after refresh; list movement verified. |

**Application journey:** The agent closed an unplanned Hour Offer sheet, remained on Restaurants, selected the requested rating order using the generic layout control adapter, and verified the refreshed list with the active filter indicator.

**Scoped assertion evidence:** The saved crops bind assertions to the relevant UI region instead of relying only on whole-screen interpretation.

**Auditable artifact folder:** The artifact structure preserves screenshots, hierarchy, OCR, decisions, assertion crops, toggle crop evidence (toggle-crop-left.png, toggle-crop-right.png with multi-tool fallback), retry metadata, and the terminal result. This captured run demonstrates the workflow; repeated-run measurements are still required to establish reliability.

---

## Key implementation files

| File | Purpose |
|---|---|
| `src/main.py` | Primary execution orchestrator; observation capture, grounding, executor, assertions, recovery coordination. |
| `src/planning.py` | AI plan compiler; natural-language normalization and validation. |
| `src/capabilities.py` | Capability registry; shared execution contract. |
| `src/adapters/base_adapter.py` | Abstract DomainAdapter interface. |
| `src/adapters/generic_adapter.py` | Generic domain-agnostic layout control grounding (~450 lines). |
| `src/recovery.py` | Optional-modal detection and dismissal strategies. |
| `run_all_tests.sh` | Suite runner; sequential execution, artifact grouping, result aggregation. |
| `cases/*.txt` | Plain-text test cases (no domain-specific code). |

