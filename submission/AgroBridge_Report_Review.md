# AgroBridge — Submission Review and Requirement Matrix

**Prepared:** 9 November 2026  
**Report:** `submission/AgroBridge_Technical_Report.docx`  
**Verified page count:** 4 pages when exported to PDF (`submission/AgroBridge_Technical_Report.pdf`), below the 5-page limit.  
**Official source used:** https://aiforgood.itu.int/event/ai-for-good-sandbox-hackathon-united-arab-emirates/ (page metadata updated 5 November 2026).

---

## A. Requirement compliance matrix

| Requirement | Status | Evidence | What is missing / risk |
|---|---|---|---|
| **1. Innovative AI application in a domain** | **Partially addressed** | Voice crop-production assistant, retrieval-grounded answers, independent policy verifier, policy-gap workspace; live Vapi path verified with supplied examples. | The report claims only crop production; livestock is out of scope. No formal farmer-usability study or benchmark. |
| **2. Country-specific knowledge base** | **Partially addressed** | 116-document catalogue (8,900 pages); 77 KB1 documents / 7,085 chunks; page-aware 1,600-character chunks with 240 overlap; metadata, E5 embeddings, ChromaDB; citations. | **Active KB2 has only 6 budget/performance documents (4,194 chunks).** The catalogue’s other 33 KB2 policy/legal/institutional documents are not active. This is the most important submission weakness. |
| **3. Use of ITU reference code for KB creation** | **Not addressed / unverified** | The project has its own ingestion pipeline and metadata catalogue. | No evidence that `CrashingGuru/ITUAIReadiness` was used or mapped. Do not claim it. If time permits, document the mapping or explicitly state the independent implementation. |
| **4. Innovative AI solution role** | **Fully addressed** | Conversation router, contextual ASR interpretation, KB1 answer agent, citation-constrained speech, voice path. | No human evaluation; English-only voice path. |
| **5. Policy and legal adviser role** | **Partially addressed** | KB2 verifier returns APPROVED / UNAPPROVED / NEEDS_REVIEW; safe referral; policy-gap graph. | Policy/legal coverage is only as broad as the active KB2 index; no formal legal review; no jurisdiction-specific rule engine. |
| **6. Institutional participant role** | **Not addressed** | The PA prompt can role-play an institution, but there is no dedicated agent with its own mandate/evidence channel. | Implement an institutional agent or explicitly scope it as future work in the demo narrative. |
| **7. Multi-agent coordination** | **Partially addressed** | LangGraph QA and gap workflows; PA/CPA structured exchange; bounded revision loop; JSONL records. | No progressive event bus or scenario orchestrator; no inter-agent message trace beyond audit fields. |
| **8. Interactive error scenarios with sequenced, chunked events** | **Partially addressed / not automated** | The report defines a four-stage scenario; stage 1 was executed live (maize fall armyworm answer, 6.5 s). Gap workflow endpoint exists. | No automated event release, scenario IDs, stage state, or institutional actor. Stage 2–4 must be demonstrated manually or implemented before the demo. |
| **9. Audit logging and chain-of-thought tracing** | **Partially addressed** | JSONL audit per turn: raw/corrected/interpreted question, intent, crop, retrieval query, citations, verification, final answer, timings, conversation/audit IDs; Vapi logs message/history counts. | No full tool-call trace; no scenario ID; no retention policy; Vapi webhook events log only event type. Hidden chain-of-thought is intentionally not exposed; structured rationale is the defensible alternative. |
| **10. Alignment with ITU-T Y.3172** | **Partially addressed** | Explicit SRC/C/PP/M/P/D/SINK and MLFO mapping in report; architectural alignment, not conformance. | No formal conformance evidence; MLFO is static LangGraph orchestration; no ML sandbox or dynamic model selection. |
| **11. Alignment with ITU AI Readiness Framework 2.0** | **Partially addressed** | Report maps all eight requested perspectives with evidence and gaps. | No readiness indicators/measurements; no open dataset release; no model card; no energy measurement. |
| **12. Local policy mapping** | **Partially addressed** | Report cites NATIP 2022–2027, National Agricultural Extension Policy, NASC Act 2019, NDPA 2023, National AI Strategy 2024, 2025 Appropriation Act and 2024 Wet Season performance. | Active KB2 does not yet contain the policy/legal sources; mapping is partly via catalogue and design, not all retrievable. Policy statuses/years need final verification against primary documents. |
| **13. Policy/standards gap identification** | **Partially addressed** | Gap categories: confirmed shortfall, potential gap, insufficient evidence; report identifies KB2 implementation gap and absence of agriculture-specific AI advice/validation standards. | No formal policy-gap benchmark or expert adjudication; global examples are illustrative, not validated for Nigeria. |
| **14. Global best practices** | **Partially addressed** | FAO/WHO pesticide code; OECD AI Principles; ITU Y.3172 and AI Readiness 2.0. | No structured comparative review of country programmes; examples are not tested for transferability. |
| **15. Technical report ≤5 pages** | **Fully addressed** | DOCX exports to 4 PDF pages; sections, tables, figure, references included. | Confirm final Word rendering on the organiser’s machine; Word’s internal page count during one check was inconsistent with the exported PDF, so the PDF page count is used as verification. |
| **16. GitHub repository** | **Presumably available** | Local repo on branch `VAPI`; MIT licence; tests. | Confirm remote URL, public access, and exclude `.env`, logs, `resources/`, indexes and `documents/` as appropriate. |
| **17. Knowledge-base materials** | **Partially addressed** | 116-document catalogue; 127 files in `documents/`; provenance and hashes. | Full KB2 reindex is outstanding; open-data publication/permissions not confirmed. |
| **18. Demo video** | **Not addressed** | No video produced. | Optional first round, required if shortlisted. Record a focused 5–7 minute demo. |

---

## B. Recommendations, prioritised

### Critical

1. **Reindex the full KB2 policy corpus and verify counts before submission.**
   - The catalogue describes 39 KB2 documents (4,864 pages), but the active Chroma collection currently contains six budget/performance documents.
   - Run `python ingest.py --kb KB2`, verify `collection_count("KB2")` and list distinct `document_name` values.
   - Re-run policy verifier and gap queries against NATIP, the National Agricultural Extension Policy, the NASC Act and the 2025 seed regulations.
   - If reindexing cannot finish, keep the report’s current honest limitation and make it explicit in the demo.

2. **Implement or stage a real progressive scenario runner.**
   - The report describes four stages; only stage 1 was executed live.
   - Add a small scenario endpoint or script that releases events one at a time, assigns a `scenario_id`, records stage, recipient agent, available evidence and output.
   - At minimum, run and record stages 1–3 before the demo; do not present the table as fully executed.

3. **Add the institutional-participant role or explicitly scope it out.**
   - A minimal agent can read a specific institution mandate from KB2 and return a bounded assessment; it does not need a new orchestration framework.
   - If not implemented, say “not implemented” in the demo and report; the current report does.

### High

4. **Add a model/version and prompt-version record to the audit.**
   - The audit currently records provider/retrieval/verification but not the exact LLM model or prompt version.
   - Add `model`, `prompt_version` and `scenario_id` fields.

5. **Publish a small open KB sample and a model card.**
   - The report claims MIT code and a structured catalogue, not an open dataset.
   - Release non-copyrighted metadata and sample chunks; document provenance, licences and update policy.

6. **Evaluate multilingual and noisy-call behaviour.**
   - The voice path is English-only and tested on text transcripts; no Hausa, Pidgin or accent evaluation.
   - Add a small reference transcript set and report term accuracy, clarification rate and task completion; do not claim WER without audio references.

7. **Harden privacy.**
   - Audio is not stored by AgroBridge and caller IDs are hashed, but a DPIA, retention schedule and consent script are missing.
   - Map NDPA 2023 obligations to the voice path; document data minimisation.

### Medium

8. Add a visible human-review/escalation path for `UNAPPROVED`/`NEEDS_REVIEW` answers.
9. Add scenario-level UI feedback for policy users: stage timeline, evidence status, confidence, source panel.
10. Add caching or precomputed embeddings for policy queries to reduce latency; record per-stage timings.
11. Add a formal requirement-to-evidence matrix as an appendix or repository document; the report is too short to carry the full matrix.

### Future

12. Build a country-pack mechanism (metadata schema + ingestion profile) for reuse beyond Nigeria.
13. Add a formal evaluation harness for agronomic correctness, citation precision and policy-gap adjudication with domain experts.
14. Explore offline/edge TTS/STT and low-bandwidth deployment.

---

## C. Diagrams to sketch

### 1. High-level architecture (already generated)
- File inserted in the DOCX: `.tmp/agrobridge_architecture.png`.
- Contents: caller → Vapi/Nova-3 → FastAPI custom LLM → LangGraph QA → spoken answer; KB1 and KB2 as separate retrieval scopes; policy workspace → PA/CPA → synthesis → gap report; audit box.
- Improvement: add a dashed arrow from policy path to KB1/KB2 and label “verification / evidence boundary.”

### 2. Progressive scenario sequence
- Vertical sequence with four lanes: Farmer, QA/Verifier, Policy Analyst/CPA, Institution.
- Stage 1: farmer reports maize leaf holes; answer agent uses KB1.
- Stage 2: farmer asks for a product/dose; verifier checks KB2 and returns safe referral or NEEDS_REVIEW.
- Stage 3: policy analyst asks about extension commitments; PA/CPA returns gap with evidence status.
- Stage 4: institution adds budget-release evidence; status changes from potential gap to confirmed shortfall or insufficient evidence.
- Add timestamps/event IDs and a visible audit trail.

### 3. Knowledge-base pipeline
- Documents → extraction → OCR sidecar → page-aware chunking (1,600/240) → metadata/citation → E5 embedding → Chroma → ranked evidence → answer/verifier.
- Show KB1 and KB2 as parallel lanes; show content-hash IDs and stale-chunk deletion.

### 4. Policy-to-evidence-to-gap workflow
- Commitment (policy text) + need (KB1) + delivery evidence (budget/performance) → PA/CPA exchange → synthesis → category: confirmed shortfall / potential gap / insufficient evidence.
- Annotate “absence of evidence is not proof of failure.”

---

## D. Research gaps and assumptions

1. **Mentoring recordings:** the official page lists Zoom recordings and passcodes, but no local transcript was found. The report does not claim to have watched them. A team member should review the sessions on scenario design, evaluation expectations and the ITU reference code.
2. **`resources/Hackathon page.pdf`:** text extraction returned blank pages (likely image-only). The official web page was used instead; verify no archived FAQ differs.
3. **Policy corpus status:** source catalogue and active KB2 differ. The report states this explicitly; do not remove the limitation without a verified reindex.
4. **Nigerian policy status:** NATIP/extension/seed/NDPA/National AI Strategy citations come from catalogue metadata and official URLs. Verify the exact policy versions/years and any amendments before final submission; especially the National Agricultural Extension Policy year and the 2025 seed regulations.
5. **Statistics:** the two headline figures are World Bank 2024 indicators. Agriculture value added includes forestry and fishing, not only crop production; the report says so. Avoid adding unsourced smallholder or extension-ratio claims.
6. **Team and repository details:** the DOCX uses “AgroBridge Team.” The official template asks for team leader/members/contact/GitHub. Fill these before submission.
7. **Formal evaluation:** no agronomic accuracy benchmark, WER, policy-gap adjudication or user study has been run. The report says so. Do not add invented metrics.

---

## E. Report limitations and compromises

- **Five-page limit:** the report is four PDF pages, so there is room for one compact table if needed. The current version prioritises the requirement mapping and the progressive scenario over a separate full literature review.
- **Policy corpus:** the report deliberately distinguishes the 116-document catalogue from the six active KB2 documents. This is less flattering but defensible.
- **Standards:** Y.3172 is presented as an architectural alignment, not formal conformance. No claim of certification is made.
- **Scenario:** only stage 1 was executed live. Stages 2–4 are marked as expected/not executed. Do not present them as observed results.
- **Voice performance:** the live 6.5 s example is an observation, not a benchmark; provider timeouts were observed and are disclosed in the review, not hidden.
- **Figure:** the architecture diagram is a static schematic, not a runtime trace.

---

## F. Final submission checklist

- [x] `submission/AgroBridge_Technical_Report.docx`
- [x] `submission/AgroBridge_Report_Review.md`
- [x] Report exported to PDF and verified at 4 pages.
- [x] Technical claims checked against current code: Vapi, Deepgram Nova-3, ElevenLabs, QA graph, verifier, gap graph, audit fields.
- [x] Current KB counts verified: KB1 7,085 chunks / 77 docs; KB2 4,194 chunks / 6 docs.
- [ ] Full KB2 policy/legal reindex and post-reindex verification.
- [ ] Team leader/member/contact details and public GitHub URL inserted.
- [ ] GitHub repository cleaned of secrets, logs, resources, indexes and local data.
- [ ] Demo video recorded (optional first round; required if shortlisted).
- [ ] Final policy versions and citations verified by a human.
- [ ] Final visual check in Microsoft Word on the submission machine.

---

## G. Three most urgent actions

1. **Reindex and verify the full KB2 policy corpus**, then re-run the policy verifier and gap workflow. This is the largest gap between the report’s design and the current active system.
2. **Implement and record a real progressive scenario** with stage IDs, event timing, agent recipients and audit entries; do not rely on the table alone.
3. **Add the official team/GitHub details** and **record a concise demo** showing the voice path, an ambiguous ASR recovery, the verifier, and the policy gap workflow.
