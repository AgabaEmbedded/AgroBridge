# AgroBridge Submission Review

**Submission file:** `submission/AgroBridge_Technical_Report.docx`  
**Verified page count:** 4 pages when exported to PDF and checked in Word. Limit: 5 pages.  
**Structure followed:** the sample submission headings: Introduction; Description of the use case; Use case requirements; Mapping with ITU-T Y.3172, AI Readiness 2.0 and domain-specific policies; Error scenarios; Policy gaps and standards gaps; References.

## What the submission covers

- Simple-language, high-level narrative; implementation details are reduced.
- The crop-production problem in Nigeria, using two current World Bank indicators (2024).
- The voice path: phone call → Vapi → Deepgram Nova-3 → custom LLM → KB1 answer → KB2 verifier → ElevenLabs voice.
- The policy path: PA/CPA exchange, synthesis and gap status.
- Y.3172 Figure 3 mapping: SRC, C, PP, M, P, D, SINK, MLFO and ML sandbox.
- Selected AI Readiness 2.0 dimensions: open data/open source; generative AI; contextualisation; cross-domain integration; human supervision; policy opportunity; social inclusion; infrastructure/energy.
- A four-step sequenced error scenario covering ASR error, unsafe advice, policy delivery and commercial controversy.
- Policy and standards gaps, with global examples.

## Full-scope assumption used in the report

The report describes the **target service scope**, not only the current demo:

- English, Nigerian Pidgin, Hausa, Igbo and Yoruba.
- Natural Nigerian-accented TTS.
- Phone-first access for low-literacy users.
- Crop-production advice with a separate policy verifier.

The current prototype is still English-first. The language and accent scope must be evaluated before claiming production readiness.

## Policy documents that would fit but are not yet in KB2

These are cross-cutting technology/AI policies used in the mapping. The report marks them with an asterisk. Download and ingest them if you want the policy claims to be directly retrievable:

1. **Nigeria Data Protection Act 2023**  
   https://www.ncc.gov.ng/sites/default/files/2024-11/Nigeria_Data_Protection_Act_2023.pdf

2. **National Artificial Intelligence Strategy 2024**  
   https://ncair.nitda.gov.ng/wp-content/uploads/2024/08/National-AI-Strategy_01082024-copy.pdf

3. **National Digital Economy Policy and Strategy 2020–2030**  
   https://nitda.gov.ng/wp-content/uploads/2020/06/National-Digital-Economy-Policy-and-Strategy.pdf

Optional infrastructure/security additions:

4. National Broadband Plan 2020–2025.
5. National Cybersecurity Policy and Strategy.

The agricultural policy documents already in KB2 include NATIP 2022–2027, the National Agricultural Extension Policy, the NASC Act 2019, the 2025 seed regulations, the 2025 Appropriation Act and the 2024 Wet Season Agricultural Performance report.

## Items still needing completion

- **Team details:** the DOCX currently says “Team members: AgroBridge team” and “Contact: to be completed.” Replace these with the official names and contact.
- **GitHub link:** the report uses `https://github.com/AgabaEmbedded/AgroBridge`. Confirm it is public and contains the intended branch.
- **Language and accent evaluation:** run a small test set in Pidgin, Hausa, Igbo and Yoruba; record recognition and task completion. Do not claim measured performance without results.
- **Institutional participant agent:** the report describes the role; it is not a separate implemented agent yet.
- **Progressive scenario runner:** the report says it is the next integration step. Add a scenario ID, stage log and event release if the demo needs to show the full sequence.
- **Policy ingestion:** download the three cross-cutting policies above and add them to KB2 if the final demo will query them.
- **Demo video:** optional for the first round; required if shortlisted.

## Known limitations in the report

- The report is 4 pages. The body uses Times New Roman 12 pt; tables use a smaller size so the mapping fits within five pages. The Y.3172 table is the main policy mapping.
- The report describes the target multilingual/accent scope, while the current demo is English-first.
- The error scenario is a design and partial-prototype description; the automated stage runner is not yet built.
- The policy gap analysis is careful to label missing evidence as insufficient evidence, not as proof that a policy failed.
- The figure is an architectural mapping, not a formal Y.3172 conformance certification.

## Final checklist

- [x] DOCX created: `submission/AgroBridge_Technical_Report.docx`
- [x] Reviewed against the sample headings.
- [x] Verified page count: 4 pages; body font Times New Roman 12 pt.
- [x] Y.3172 Figure 3 nodes mapped in a table and diagram.
- [x] AI Readiness dimensions selected and explained.
- [x] Policy mapping includes agricultural and technology/AI documents.
- [x] Error scenario includes technical and policy/controversy stages.
- [ ] Team leader/member/contact details completed.
- [ ] Three cross-cutting policy PDFs downloaded and ingested (if needed for the final demo).
- [ ] Language/accent evaluation recorded.
- [ ] Demo video recorded if required.
