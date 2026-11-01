# AGROBRIDGE – IMPLEMENTATION INSTRUCTION
## Independent Question-Answer and Multi-Agent Gap Analysis Architecture

### 1. Project Objective

Refactor and extend the existing AgroBridge project into two independent AI workflows:

1. **Question-Answer Agent:** A farmer-facing agricultural assistant primarily accessed through telephone calls using Voicebip.
2. **Gap Analysis Agent:** A multi-agent agricultural policy intelligence system accessed through the web interface (to be built later).

Both systems must use the same underlying LLM infrastructure, embedding service and document processing infrastructure, while maintaining separate agent workflows.

IMPORTANT: Before implementing anything, inspect the existing project and understand its current architecture.

- Preserve existing working functionality.
- Do not unnecessarily rewrite existing code.
- Reuse existing FastAPI, Voicebip, LLM, RAG and configuration implementations where possible.
- Adapt the proposed architecture to the actual project structure.
- Implement incrementally and test each major component.

Do not introduce a global triage node. The two systems have separate entry points and independent workflows.

---

# 2. Knowledge Base Organisation

I will create a `documents` directory in the project root.

Use the following structure:

```text
AgroBridge/
│
├── documents/
│   ├── KB1/
│   │   
│   └── KB2/
│       
```

## KB1 – Agricultural Knowledge Base

Location: `documents/KB1/`

intended to contain regular agricultural knowledge:

- Crop production manuals.
- Crop diseases and their management.
- Pest identification and management.
- Fertilizer application and soil management.
- Irrigation and water management.
- Planting and harvesting practices.
- Livestock management, if supported.
- Agricultural research and technical guides.

Purpose: Support practical agricultural questions from farmers.

## KB2 – Agricultural Policy Knowledge Base

Location: `documents/KB2/`

Intended to contain:

- National agricultural policies.
- Agricultural extension policies.
- Government regulations and legislation.
- Government implementation reports.
- Agricultural budgets and expenditure reports.
- Institutional responsibilities.
- Government agricultural programmes.
- International agricultural frameworks.

Purpose:
1. Support policy compliance verification in the Question-Answer workflow.
2. Support policy analysis and gap identification in the Gap Analysis workflow.

IMPORTANT: KB2 must contain implementation evidence in addition to policy documents. A policy document establishes government commitments, but implementation reports, budgets and evaluation reports help assess actual progress.

## Document ingestion requirements

Implement separate KB1 and KB2 ingestion pipelines or logically isolated collections.

The system should:

- Automatically discover supported documents inside the respective directories.
- Support PDF, DOCX and TXT.
- Extract document text and preserve page information where possible.
- Chunk documents appropriately.
- Generate embeddings.
- Store document metadata.
- Avoid re-embedding unchanged documents.
- Detect newly added and modified documents.
- Support document deletion and re-indexing.

Every chunk should retain metadata such as:

```python
{
    "document_name": "",
    "knowledge_base": "KB1",
    "document_type": "",
    "source": "",
    "publication_year": None,
    "page_number": None,
    "category": "",
    "source_path": ""
}
```

Use `KB2` as the corresponding knowledge-base value for policy documents.

Do not hardcode document names.

Keep the embedding service independent of the generation LLM. Do not download the embedding model every time the application starts or ingestion runs.

---

# 3. OVERALL APPLICATION ARCHITECTURE

Implement two independent workflows, fine the architecture in architecture.jpg and also below

```text
                QUESTION-ANSWER SYSTEM
                ======================

                  VOICE INPUT
                       |
                       v
               AGROBRIDGE AGENT
                       |
                    KB1 TOOLS
                       |
                       v
                 GENERATED ANSWER
                       |
                       v
                 VERIFIER AGENT
                       |
                    KB2 TOOLS
                       |
                 POLICY CHECK
                       |
                +------+------+
                |             |
                v             v
             APPROVED      UNAPPROVED
                |             |
                v             v
              OUTPUT      AGROBRIDGE
                          AGENT REVISION


                  GAP ANALYSIS SYSTEM
                  ===================

                   WEB INPUT
                       |
                       v
               GAP ANALYSIS AGENT 1
                       |
                    KB2 TOOLS
                       |
                       v
               GAP ANALYSIS AGENT 2
                       |
                    KB1 TOOLS
                       |
                       v
                AGENT COMMUNICATION
                       |
                       v
                SYNTHESIS NODE
                       |
                       v
                    OUTPUT
```

The two systems should have separate orchestration graphs and entry points.

They may share:
- LLM service.
- Embedding service.
- Vector database infrastructure.
- Document ingestion services.
- Logging infrastructure.
- Common utility functions.

They must not share the same agent execution graph.

when the architecture here conflicts with architecture.jpg, architecure.jpg should be the object of truth

---

# 4. QUESTION-ANSWER AGENT

This workflow is primarily accessed through the existing Voicebip telephone integration.

Its purpose is to provide farmers with practical agricultural assistance.

## 4.1 AgroBridge Agent

The AgroBridge Agent is responsible for:

1. Receiving the farmer's question.
2. Understanding the agricultural problem.
3. Identifying the relevant crop or agricultural activity.
4. Retrieving relevant information from KB1.
5. Generating an understandable and practical answer.
6. Returning the answer alongside supporting evidence.
7. Passing the proposed answer to the Verifier Agent.

It should have access to KB1 through its own retrieval tools.

Examples of supported questions:

- How do I identify fall armyworm in maize?
- What fertilizer is suitable for rice?
- How do I manage tomato blight?
- When should I plant maize?
- How can I improve soil fertility?

### Response requirements

- Prefer Nigerian agricultural information.
- Use simple language suitable for farmers.
- Avoid presenting uncertain disease identification as confirmed diagnosis.
- Never invent fertilizer application rates or pesticide recommendations.
- Communicate uncertainty when information is insufficient.
- Preserve citations and source references.

The agent should return structured data containing:

```python
{
    "answer": "",
    "recommendations": [],
    "supporting_evidence": [],
    "citations": [],
    "confidence": ""
}
```

## 4.2 Verifier Agent

This is a policy-compliance agent, not merely a factuality checker.

Its primary responsibility is to determine whether recommendations generated by the AgroBridge Agent are consistent with applicable government agricultural policies, regulations, official guidelines and standards.

It must have independent access to KB2 through verification tools.

### Verification workflow

1. Receive the proposed answer from AgroBridge Agent.
2. Extract the recommendations and relevant claims.
3. Identify applicable policy and regulatory requirements.
4. Retrieve relevant passages from KB2.
5. Compare the recommendations against the retrieved requirements.
6. Determine whether conflicts exist.
7. Return a structured verification result.

### Verification outcomes

Use three possible outcomes:

**APPROVED**

No conflict with applicable requirements has been identified in the available evidence.

**UNAPPROVED**

An identifiable conflict exists between the recommendation and an applicable policy provision, regulation or official requirement.

**NEEDS_REVIEW**

Available documents are insufficient to establish whether the recommendation complies.

Important considerations:

- Absence of a policy document must not automatically mean rejection.
- Do not assume every agricultural recommendation must be explicitly mentioned in a government policy.
- Do not interpret broad policy objectives as technical agricultural requirements.
- Give greater weight to applicable regulations and official technical standards when assessing regulated activities.
- Preserve the exact document and page supporting a compliance decision.

### Revision feedback loop

If the verifier returns UNAPPROVED:

1. Send the conflict and supporting policy evidence to the AgroBridge Agent.
2. Ask it to revise its recommendation.
3. Pass the revised answer back to the Verifier.
4. Repeat verification.

Set a configurable maximum of two revision attempts.

If verification still fails, do not return an unverified recommendation as approved.

For NEEDS_REVIEW, communicate the uncertainty appropriately rather than forcing an approval or rejection.

Example verifier response:

```python
{
    "status": "UNAPPROVED",
    "policy_conflicts": [],
    "supporting_policy_evidence": [],
    "citations": [],
    "revision_instructions": [],
    "reasoning_summary": ""
}
```

### Important

The Verifier must independently retrieve relevant information from KB2. Do not simply ask the AgroBridge Agent whether its own response complies.

---

# 5. GAP ANALYSIS MULTI-AGENT SYSTEM

This is an independent workflow accessed primarily through the AgroBridge web interface to be buillt later but include FastAPI endpoint to access it.

Its purpose is to analyse agricultural policies, identify practical agricultural needs and investigate gaps between policy commitments and agricultural realities.

It must contain two specialised agents with different knowledge sources and responsibilities.

## 5.1 Gap Analysis Agent 1 – Policy and Institutional Analyst

Knowledge base: KB2.

This agent focuses on government policies, institutional commitments and implementation evidence.

Responsibilities:

1. Retrieve relevant national agricultural policies.
2. Extract policy objectives and commitments.
3. Identify implementation targets and timelines.
4. Identify responsible institutions.
5. Retrieve relevant implementation reports.
6. Examine available budget allocations and programme evidence.
7. Identify the extent to which available evidence demonstrates implementation.
8. Return its findings to Gap Analysis Agent 2.

It should distinguish between:

- Government commitments.
- Planned activities.
- Budget allocations.
- Actual implementation evidence.
- Measured outcomes.

It must not assume a policy commitment has been implemented simply because it appears in a government document.

Example structured output:

```python
{
    "policy_commitments": [],
    "responsible_institutions": [],
    "implementation_targets": [],
    "implementation_evidence": [],
    "identified_policy_gaps": [],
    "citations": []
}
```

## 5.2 Gap Analysis Agent 2 – Agricultural Needs Analyst

Knowledge base: KB1.

This agent focuses on practical agricultural realities and farmers' needs.

Responsibilities:

1. Retrieve relevant agricultural research and technical guides.
2. Identify practical challenges farmers face in the relevant agricultural area.
3. Identify the services, resources and interventions needed to address those challenges.
4. Establish technical and operational requirements for improving agricultural productivity.
5. Identify agricultural needs that may not be adequately addressed by existing policy commitments.
6. Review the findings from Gap Analysis Agent 1.
7. Return its independent assessment and feedback.

It must not simply repeat Agent 1's policy analysis.

Example structured output:

```python
{
    "agricultural_challenges": [],
    "practical_farmer_needs": [],
    "technical_requirements": [],
    "evidence_of_challenges": [],
    "policy_coverage_observations": [],
    "citations": []
}
```

## 5.3 Agent-to-Agent Communication

The agents must exchange findings before the final analysis is produced.

This is a core requirement, not an optional feature.

The communication should allow:

- Agent 1 to explain relevant policy commitments and implementation findings.
- Agent 2 to explain practical agricultural requirements and challenges.
- Agent 2 to identify needs that may be overlooked in the policies.
- Agent 1 to clarify whether relevant commitments or programmes already address those needs.
- Both agents to identify missing information and unsupported assumptions.
- Additional retrieval where necessary.

Do not implement two agents that independently generate answers and simply concatenate them.

The interaction must contribute to the actual analysis.

Use structured agent messages rather than unrestricted conversational exchanges.

Implement a configurable communication limit to prevent endless agent discussions.

## 5.4 Synthesis Node

After agent communication, introduce a dedicated synthesis node.

This node receives:

- Agent 1's policy findings.
- Agent 2's agricultural needs assessment.
- Their communication history.
- Supporting evidence and citations.

It consolidates the findings into a coherent gap analysis.

The final report should identify:

### A. Policy Coverage Gaps

Agricultural needs that are not adequately addressed by identified policy commitments.

### B. Implementation Gaps

Policy commitments for which available evidence demonstrates incomplete implementation or measurable shortfalls.

### C. Institutional Gaps

Unclear responsibilities, overlapping mandates or coordination issues supported by evidence.

### D. Evidence Gaps

Areas where available information is insufficient to establish whether commitments have been implemented.

For every identified gap, include:

- Gap description.
- Relevant policy commitment.
- Practical agricultural need.
- Available implementation evidence.
- Responsible institution, where identifiable.
- Supporting citations.
- Evidence status or confidence.

IMPORTANT:

Do not automatically conclude that government has failed because an implementation report was not retrieved.

Clearly distinguish between:
- Confirmed shortfall.
- Potential gap.
- Insufficient evidence.

---

#### 6. TOOLS AND RETRIEVAL SERVICES

Implement a small, reusable retrieval-tool layer rather than creating numerous narrowly specialised tools.

The initial tool interfaces should be:

- `search_kb1(query, filters=None, top_k=None)`: Searches the agricultural knowledge base and returns relevant passages.
- `search_kb2(query, filters=None, top_k=None)`: Searches the agricultural policy knowledge base and returns relevant passages.
- `get_document(document_id, page_number=None)`: Retrieves additional content from an ingested source document when necessary.

Adapt these interfaces to the existing RAG implementation where possible.

The search tools should support metadata filtering, including document category, crop, document type, publication year and other relevant metadata.

#### Tool access

- AgroBridge Agent: KB1 retrieval tools.
- Verifier Agent: KB2 retrieval tools.
- Gap Analysis Agent 1: KB2 retrieval tools.
- Gap Analysis Agent 2: KB1 retrieval tools.

Agents may share the same underlying retrieval service, but must retain separate responsibilities and appropriately scoped tool access.

#### Retrieval results

Every retrieval operation should return:

- Relevant text chunks.
- Document name and unique document ID.
- Page number, where available.
- Source information.
- Knowledge base identifier.
- Relevant document metadata.
- A traceable citation reference.

The agents must use retrieved evidence when producing factual claims and must not fabricate citations.

Policy-specific retrieval strategies, such as finding policy commitments, implementation reports or institutional responsibilities, should initially be implemented through search queries and metadata filters rather than creating separate tools for every operation.

Similarly, the Verifier Agent must perform policy-compliance reasoning using retrieved evidence rather than relying on a standalone `compare_recommendations()` retrieval tool.

Keep the retrieval layer modular so specialised tools can be introduced later when genuinely necessary.

# 7. ORCHESTRATION AND STATE MANAGEMENT

Use LangGraph if compatible with the existing project.

Implement two independent graphs:

1. Question-Answer Graph.
2. Gap Analysis Graph.

The Question-Answer graph should manage:

```text
Input
  ↓
AgroBridge Agent
  ↓
Verifier Agent
  ↓
Approved? 
  ├── Yes → Output
  └── No → Revision → Verifier
```

The Gap Analysis graph should manage:

```text
Input
  ↓
GA Agent 1
  ↓
GA Agent 2
  ↓
Agent communication
  ↓
Synthesis
  ↓
Output
```

The agents should communicate through shared typed state and structured messages.

Maintain independent state for each workflow.

Avoid unnecessary global state.

The state should preserve:

- Original user input.
- Agent outputs.
- Retrieved evidence.
- Citations.
- Agent communication history.
- Verification results.
- Revision count.
- Final output.
- Audit information.

---

# 8. APPLICATION INTERFACE AND INTEGRATION

Maintain two separate application entry points.

### Question-Answer workflow

Input source: Existing Voicebip webhook.

The existing Voicebip integration should continue to:
- Receive call events.
- Receive farmer transcriptions.
- Send farmer queries into the Question-Answer graph.
- Return generated responses in the expected Voicebip format.

Preserve existing webhook event handling and response contracts.

The voice workflow should prioritise low latency and concise answers.

### Gap Analysis workflow

Input source: Web interface.

Expose an independent API endpoint for policy analysis requests.

For example:

```text
POST /api/gap-analysis
```

The endpoint should:
- Accept a policy analysis query.
- Start the Gap Analysis graph.
- Return the final analysis.
- Preserve citations and supporting evidence.

Adapt the endpoint to the existing API conventions.

Do not route web policy analysis requests through the Voicebip webhook.

---

# 9. SHARED LLM AND EMBEDDING INFRASTRUCTURE

Both workflows should reuse shared services.

Suggested structure:

```text
services/
│
├── llm_service.py
├── embedding_service.py
├── retrieval_service.py
├── document_processor.py
└── audit_service.py
```

Requirements:

- Centralise LLM configuration.
- Read API keys from environment variables.
- Do not hardcode model names across agent files.
- Keep embedding and generation models independent.
- Handle timeouts and API errors.
- Use structured outputs where appropriate.
- Avoid unnecessary model calls.
- Make agent communication limits configurable.

Do not assume the LLM provider also provides embeddings.

Inspect the existing embedding implementation before changing it.

---

# 10. AUDIT LOGGING AND TRACEABILITY

Maintain an audit trail for both workflows.

For each request, record:

- Original input.
- Workflow activated.
- Agents invoked.
- Knowledge bases accessed.
- Retrieved document references.
- Agent outputs.
- Agent communication.
- Verification results, where applicable.
- Revision attempts.
- Final response.

For the Gap Analysis system, preserve the interaction between GA Agent 1 and GA Agent 2.

For the Question-Answer system, preserve the Verifier's assessment and any revisions.

Do not log secrets, API keys or passwords.

---

# 11. ERROR HANDLING AND SAFETY

Implement appropriate handling for:

- No relevant documents retrieved.
- Empty or unreadable documents.
- LLM API failures.
- Embedding failures.
- Vector database errors.
- Invalid structured model outputs.
- Agent communication failures.
- Verification failures.
- Exceeded revision limits.

The system must not fabricate information or citations when retrieval fails.

When evidence is insufficient, communicate that limitation.

For agricultural recommendations involving pesticides, fertilizers or other regulated inputs, do not generate unsupported technical instructions.

---

# 12. IMPLEMENTATION SEQUENCE

Implement incrementally.

### Stage 1: Inspect existing codebase
Understand the existing implementation and report the proposed changes.

### Stage 2: Knowledge base infrastructure
Implement separate KB1 and KB2 ingestion and retrieval.

### Stage 3: Question-Answer workflow
Implement AgroBridge Agent and KB1 retrieval.

### Stage 4: Verifier workflow
Implement KB2 policy retrieval, compliance assessment and revision feedback.

### Stage 5: Gap Analysis Agent 1
Implement policy and institutional analysis using KB2.

### Stage 6: Gap Analysis Agent 2
Implement agricultural needs analysis using KB1.

### Stage 7: Agent communication and synthesis
Implement structured communication and the final synthesis node.

### Stage 8: Application integration
Connect the Question-Answer graph to Voicebip and expose the Gap Analysis graph through the web API.

### Stage 9: Audit logging
Implement workflow traceability.

### Stage 10: End-to-end testing
Test both workflows independently and together with their existing integrations.

---

# 13. ACCEPTANCE CRITERIA

The implementation is complete when:

**Question-Answer System**

1. A farmer can submit a question through Voicebip.
2. AgroBridge Agent retrieves relevant information from KB1.
3. It generates an answer with supporting citations.
4. The Verifier independently checks applicable policy requirements using KB2.
5. The Verifier can return APPROVED, UNAPPROVED or NEEDS_REVIEW.
6. Unapproved responses can be revised and rechecked.
7. The existing Voicebip integration remains functional.

**Gap Analysis System**

8. A user can submit a policy analysis request through the web API.
9. GA Agent 1 retrieves policy and implementation evidence from KB2.
10. GA Agent 2 retrieves agricultural needs and technical information from KB1.
11. Both agents exchange findings before synthesis.
12. The synthesis node produces a consolidated gap analysis.
13. The analysis distinguishes policy coverage, implementation, institutional and evidence gaps.
14. Important conclusions have traceable supporting citations.

**Infrastructure**

15. KB1 and KB2 remain logically separate.
16. Documents can be added without modifying application code.
17. Existing working functionality is preserved.
18. Both workflows maintain independent audit trails.
19. Errors and insufficient evidence are handled appropriately.

---

# 14. FINAL DELIVERABLES

After implementation, provide:

1. Summary of the final architecture.
2. Updated project directory structure.
3. List of modified and newly created files.
4. Dependencies added or removed.
5. Instructions for adding and ingesting documents into KB1 and KB2.
6. Instructions for running both workflows.
7. API endpoint documentation.
8. Results of tests actually performed.
9. Known limitations and incomplete functionality.

Do not claim that functionality works unless it has been implemented and tested.

## Final architectural instruction

The objective is not to create as many agents as possible.

Every agent must have a distinct responsibility and a meaningful contribution.

Maintain two independent systems:

- Question-Answer Agent: farmer assistance with policy compliance verification.
- Gap Analysis Multi-Agent System: collaborative policy and agricultural needs analysis.

Prioritise modularity, evidence traceability, reliable retrieval, predictable orchestration and maintainability over unnecessary complexity.