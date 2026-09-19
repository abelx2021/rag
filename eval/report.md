# RAG evaluation — architecture failure map

Corpus: 80 chunks / 12 documents (~35k chars). Rerank tokens this run: 92,227 in / 213 out.

## Hit rate by question type (final top-3 after rerank)

| type | n | hit@3 | vec hit@10 | merged hit | rerank losses |
|---|---|---|---|---|---|
| direct | 16 | 15/16 | 14/16 | 15/16 | 0 |
| synthesis | 6 | 6/6 | 6/6 | 6/6 | 0 |
| id | 6 | 6/6 | 6/6 | 6/6 | 0 |
| numeric | 5 | 5/5 | 5/5 | 5/5 | 0 |
| obscure | 3 | 3/3 | 3/3 | 3/3 | 0 |

Overall (answerable questions): hit@3 = 35/36
Vector hit@10 = 34/36; merged recall = 35/36
Graph layer contributed a chunk the vector stage never surfaced in 36/36 questions; it reached the final answer in 9.

## Failure attribution

### direct
- d01 hit — How does IANUS send monitoring data to RGS?
  - expected: ['puc-rgs-regis-snm-connector::Transmission flow']
  - vec best rank None (top score 0.5606), graph hit True, merged True, seed 'ianus-platform'
  - rerank said '10,3,9' → final: ['puc-rgs-regis-snm-connector::Transmission flow (graph)', 'puc-rgs-regis-snm-connector::Introduction (vector)', 'puc-rgs-regis-snm-connector::What it exchanges (vector)']
- d02 hit — What is the object key format used for stored files?
  - expected: ['document-pipeline::Data / file separation']
  - vec best rank 1 (top score 0.5975), graph hit False, merged True, seed 'document-pipeline'
  - rerank said '0,4,6' → final: ['document-pipeline::Data / file separation (vector)', 'document-pipeline::Pipeline (vector)', 'document-pipeline::Versions, replacement, retention (vector)']
- d03 hit — What are the steps of the document upload pipeline?
  - expected: ['document-pipeline::Pipeline']
  - vec best rank 1 (top score 0.7977), graph hit False, merged True, seed 'document-pipeline'
  - rerank said '0,3,1' → final: ['document-pipeline::Pipeline (vector)', 'document-pipeline::Introduction (vector)', 'document-pipeline::Data / file separation (vector)']
- d04 hit — Which schemas make up the IANUS database?
  - expected: ['data-model::Organization']
  - vec best rank 3 (top score 0.7238), graph hit False, merged True, seed 'data-model'
  - rerank said '1,2,7' → final: ['ianus-modular-analysis-and-implementation-plan::Architectural proposal > Proposed schema organisation (vector)', 'data-model::Organization (vector)', 'ianus-technical-operational-project-document::Architecture and scope (vector)']
- d05 hit — What precision are monetary amounts stored with?
  - expected: ['data-model::Types, constraints, indices']
  - vec best rank 1 (top score 0.5375), graph hit False, merged True, seed 'data-model'
  - rerank said '0,5,7' → final: ['data-model::Types, constraints, indices (vector)', 'data-model::Introduction (vector)', 'data-model::Organization (vector)']
- d06 hit — What is the technology baseline for frontend and backend?
  - expected: ['modular-monolith-architecture::Technology baseline']
  - vec best rank 1 (top score 0.6372), graph hit False, merged True, seed 'modular-monolith-architecture'
  - rerank said '0,4,3' → final: ['modular-monolith-architecture::Technology baseline (vector)', 'ianus-modular-analysis-and-implementation-plan::Architectural proposal (vector)', 'ianus-modular-analysis-and-implementation-plan::Common technical activities (vector)']
- d07 hit — What is the repository structure of the solution?
  - expected: ['modular-monolith-architecture::Repository structure']
  - vec best rank 1 (top score 0.6578), graph hit False, merged True, seed 'modular-monolith-architecture'
  - rerank said '0,3,4' → final: ['modular-monolith-architecture::Repository structure (vector)', 'module-creation-checklist::Architecture and code boundaries (vector)', 'modular-monolith-architecture::ADR-001 — Modular monolith (vector)']
- d08 hit — What happens when a module is deactivated?
  - expected: ['module-catalog::Activation / deactivation']
  - vec best rank 1 (top score 0.7495), graph hit False, merged True, seed 'module-catalog'
  - rerank said '0,1,2' → final: ['module-catalog::Activation / deactivation (vector)', 'module-creation-checklist::Modularity principles to satisfy (vector)', 'module-catalog::Modularity principles (vector)']
- d09 hit — Which module dependencies are mandatory?
  - expected: ['module-catalog::Dependency matrix']
  - vec best rank 1 (top score 0.6946), graph hit False, merged True, seed 'module-catalog'
  - rerank said '0,5,2' → final: ['module-catalog::Dependency matrix (vector)', 'ianus-modular-analysis-and-implementation-plan::Modules (vector)', 'module-catalog::Modularity principles (vector)']
- d10 hit — What does the technical audit trail record?
  - expected: ['audit-trail::Technical audit trail']
  - vec best rank 1 (top score 0.7366), graph hit False, merged True, seed 'audit-trail'
  - rerank said '0,2,1' → final: ['audit-trail::Technical audit trail (vector)', 'module-creation-checklist::Audit and observability (vector)', 'audit-trail::Introduction (vector)']
- d11 hit — How are document versions replaced and retained?
  - expected: ['document-pipeline::Versions, replacement, retention']
  - vec best rank 1 (top score 0.7633), graph hit False, merged True, seed 'document-pipeline'
  - rerank said '0,3,2' → final: ['document-pipeline::Versions, replacement, retention (vector)', 'document-pipeline::Pipeline (vector)', 'document-pipeline::Data / file separation (vector)']
- d12 hit — Which IAM components does IANUS use?
  - expected: ['identity-and-access-management::IAM components']
  - vec best rank 3 (top score 0.7921), graph hit False, merged True, seed 'identity-and-access-management'
  - rerank said '2,0,16' → final: ['identity-and-access-management::IAM components (vector)', 'identity-and-access-management::Introduction (vector)', 'ianus-technical-operational-project-document::Confirmed decisions (graph)']
- d13 hit — How is instance isolation enforced?
  - expected: ['instance-isolation::Enforcement points']
  - vec best rank 1 (top score 0.7416), graph hit False, merged True, seed 'instance-isolation'
  - rerank said '0,12,1' → final: ['instance-isolation::Enforcement points (vector)', 'data-model::Common columns and ownership (graph)', 'instance-isolation::Security and testing (vector)']
- d14 FAIL @ retrieval (embedding+graph) — What are the nine IANUS modules?
  - expected: ['module-catalog::Modules']
  - vec best rank None (top score 0.7815), graph hit False, merged False, seed 'module-catalog'
  - rerank said '1,0,7' → final: ['ianus-modular-analysis-and-implementation-plan::Modules (vector)', 'module-catalog::Introduction (vector)', 'ianus-technical-operational-project-document::Architecture and scope (vector)']
- d15 hit — What tables exist in each database schema?
  - expected: ['data-model::Table catalog']
  - vec best rank 1 (top score 0.6219), graph hit False, merged True, seed 'data-model'
  - rerank said '0,2,3' → final: ['data-model::Table catalog (vector)', 'data-model::Organization (vector)', 'ianus-modular-analysis-and-implementation-plan::Architectural proposal > Proposed schema organisation (vector)']
- d16 hit — What is the architectural decision ADR-001?
  - expected: ['modular-monolith-architecture::ADR-001 — Modular monolith']
  - vec best rank 1 (top score 0.6014), graph hit False, merged True, seed 'modular-monolith-architecture'
  - rerank said '0,1,3' → final: ['modular-monolith-architecture::ADR-001 — Modular monolith (vector)', 'modular-monolith-architecture::Introduction (vector)', 'module-creation-checklist::Architecture and code boundaries (vector)']
### synthesis
- s01 hit — What must a new module do about enablement checks in the frontend?
  - expected: ['module-catalog::Modularity principles', 'module-creation-checklist::Frontend', 'module-creation-checklist::Modularity principles to satisfy']
  - vec best rank 1 (top score 0.6852), graph hit True, merged True, seed 'module-creation-checklist'
  - rerank said '1,4,5' → final: ['module-creation-checklist::Modularity principles to satisfy (vector)', 'module-catalog::Modularity principles (vector)', 'ianus-modular-analysis-and-implementation-plan::Modularity principles (vector)']
- s02 hit — What are the quality gates a new module must pass?
  - expected: ['module-creation-checklist::Quality gates']
  - vec best rank 1 (top score 0.7286), graph hit False, merged True, seed 'module-creation-checklist'
  - rerank said '0,1,3' → final: ['module-creation-checklist::Quality gates (vector)', 'module-creation-checklist::Modularity principles to satisfy (vector)', 'module-catalog::Modularity principles (vector)']
- s03 hit — What arguments ruled out a microservices architecture?
  - expected: ['ianus-modular-analysis-and-implementation-plan::Architectural proposal', 'modular-monolith-architecture::ADR-001 — Modular monolith']
  - vec best rank 1 (top score 0.6089), graph hit True, merged True, seed 'modular-monolith-architecture'
  - rerank said '3,6,0' → final: ['modular-monolith-architecture::Why a single database (vector)', 'ianus-modular-analysis-and-implementation-plan::Architectural proposal > Why a single database (vector)', 'modular-monolith-architecture::ADR-001 — Modular monolith (vector)']
- s04 hit — Why does IANUS use a single database instead of one per module?
  - expected: ['ianus-modular-analysis-and-implementation-plan::Architectural proposal > Why a single database', 'modular-monolith-architecture::Why a single database']
  - vec best rank 1 (top score 0.7738), graph hit True, merged True, seed 'ianus-modular-analysis-and-implementation-plan'
  - rerank said '0,1,8' → final: ['ianus-modular-analysis-and-implementation-plan::Architectural proposal > Why a single database (vector)', 'modular-monolith-architecture::Why a single database (vector)', 'ianus-modular-analysis-and-implementation-plan::Architectural proposal (vector)']
- s05 hit — What data layer rules must a new module follow?
  - expected: ['module-creation-checklist::Data layer']
  - vec best rank 1 (top score 0.6878), graph hit False, merged True, seed 'module-creation-checklist'
  - rerank said '0,13,9' → final: ['module-creation-checklist::Data layer (vector)', 'data-model::Transactions and migrations (graph)', 'data-model::Types, constraints, indices (vector)']
- s06 hit — What are the mandatory architectural principles?
  - expected: ['modular-monolith-architecture::Mandatory principles']
  - vec best rank 1 (top score 0.694), graph hit False, merged True, seed 'modular-monolith-architecture'
  - rerank said '0,4,2' → final: ['modular-monolith-architecture::Mandatory principles (vector)', 'modular-monolith-architecture::ADR-001 — Modular monolith (vector)', 'module-catalog::Modularity principles (vector)']
### id
- i01 hit — What does INT-PUC-006 require?
  - expected: ['puc-rgs-regis-snm-connector::Key rules (INT-PUC-*)']
  - vec best rank 2 (top score 0.5263), graph hit True, merged True, seed 'ianus-technical-operational-project-document'
  - rerank said '1,8,9' → final: ['puc-rgs-regis-snm-connector::Key rules (INT-PUC-*) (vector)', 'puc-rgs-regis-snm-connector::Transmission flow (vector)', 'puc-rgs-regis-snm-connector::Channels and services (vector)']
- i02 hit — What is SEC-IAM-005?
  - expected: ['identity-and-access-management::Confirmed approach']
  - vec best rank 1 (top score 0.5477), graph hit False, merged True, seed 'identity-and-access-management'
  - rerank said '0,10,2' → final: ['identity-and-access-management::Confirmed approach (vector)', 'ianus-technical-operational-project-document::Confirmed decisions (graph)', 'identity-and-access-management::Introduction (vector)']
- i03 hit — What is risk RSK-04 and how is it mitigated?
  - expected: ['instance-isolation::Security and testing']
  - vec best rank 1 (top score 0.6834), graph hit False, merged True, seed 'instance-isolation'
  - rerank said '0,6,12' → final: ['instance-isolation::Security and testing (vector)', 'ianus-technical-operational-project-document::Delivery and status (vector)', 'ianus-technical-operational-project-document::Confirmed decisions (graph)']
- i04 hit — Which Sprint 0 decisions must be closed before committing release dates?
  - expected: ['ianus-technical-operational-project-document::Delivery and status']
  - vec best rank 1 (top score 0.5758), graph hit False, merged True, seed 'ianus-technical-operational-project-document'
  - rerank said '0' → final: ['ianus-technical-operational-project-document::Delivery and status (vector)']
- i05 hit — What is DEC-CNF-01?
  - expected: ['ianus-technical-operational-project-document::Confirmed decisions', 'instance-isolation::The decision']
  - vec best rank 1 (top score 0.5318), graph hit True, merged True, seed 'instance-isolation'
  - rerank said '0,1,2' → final: ['instance-isolation::The decision (vector)', 'instance-isolation::Introduction (vector)', 'ianus-technical-operational-project-document::Confirmed decisions (vector)']
- i06 hit — How many epics does the initial backlog contain?
  - expected: ['ianus-technical-operational-project-document::Delivery and status']
  - vec best rank 1 (top score 0.5321), graph hit False, merged True, seed 'ianus-technical-operational-project-document'
  - rerank said '0,3,10' → final: ['ianus-technical-operational-project-document::Delivery and status (vector)', 'ianus-technical-operational-project-document::What this document is (vector)', 'module-catalog::Introduction (graph)']
### numeric
- n01 hit — How many validation codes can a pre-validation return and who is authoritative?
  - expected: ['puc-rgs-regis-snm-connector::Channels and services', 'puc-rgs-regis-snm-connector::Key rules (INT-PUC-*)']
  - vec best rank 1 (top score 0.48), graph hit False, merged True, seed 'puc-rgs-regis-snm-connector'
  - rerank said '0,1,13' → final: ['puc-rgs-regis-snm-connector::Channels and services (vector)', 'puc-rgs-regis-snm-connector::Transmission flow (vector)', 'ianus-technical-operational-project-document::What this document is (graph)']
- n02 hit — How many TC sheets are in the context table snapshot?
  - expected: ['puc-rgs-regis-snm-connector::Channels and services']
  - vec best rank 2 (top score 0.4872), graph hit False, merged True, seed 'data-model'
  - rerank said '1,13,6' → final: ['puc-rgs-regis-snm-connector::Channels and services (vector)', 'ianus-technical-operational-project-document::What this document is (graph)', 'puc-rgs-regis-snm-connector::What it exchanges (vector)']
- n03 hit — How many information structures does PUC 4.0 describe?
  - expected: ['puc-rgs-regis-snm-connector::What it exchanges']
  - vec best rank 1 (top score 0.7552), graph hit False, merged True, seed 'puc-rgs-regis-snm-connector'
  - rerank said '0,4,7' → final: ['puc-rgs-regis-snm-connector::What it exchanges (vector)', 'puc-rgs-regis-snm-connector::Channels and services (vector)', 'puc-rgs-regis-snm-connector::Transmission flow (vector)']
- n04 hit — What decimal precision is used for percentages and quantities?
  - expected: ['data-model::Types, constraints, indices']
  - vec best rank 1 (top score 0.5444), graph hit False, merged True, seed 'data-model'
  - rerank said '0,4,5' → final: ['data-model::Types, constraints, indices (vector)', 'module-creation-checklist::Data layer (vector)', 'data-model::Organization (vector)']
- n05 hit — How many phases does the implementation plan have?
  - expected: ['ianus-technical-operational-project-document::Delivery and status']
  - vec best rank 1 (top score 0.5662), graph hit False, merged True, seed 'ianus-technical-operational-project-document'
  - rerank said '0,4,3' → final: ['ianus-technical-operational-project-document::Delivery and status (vector)', 'ianus-modular-analysis-and-implementation-plan::What this document is (vector)', 'ianus-modular-analysis-and-implementation-plan::Introduction (vector)']
### obscure
- o01 hit — Which documents is the IANUS platform specified in?
  - expected: ['ianus-platform::Specified in']
  - vec best rank 1 (top score 0.7592), graph hit False, merged True, seed 'ianus-platform'
  - rerank said '0,1,9' → final: ['ianus-platform::Specified in (vector)', 'ianus-technical-operational-project-document::What this document is (vector)', 'ianus-technical-operational-project-document::Introduction (vector)']
- o02 hit — What does the vault say about functional audit as opposed to technical audit?
  - expected: ['audit-trail::Functional audit', 'audit-trail::Technical audit trail']
  - vec best rank 3 (top score 0.6536), graph hit True, merged True, seed 'ianus-modular-analysis-and-implementation-plan'
  - rerank said '1,0,3' → final: ['audit-trail::Introduction (vector)', 'ianus-modular-analysis-and-implementation-plan::Audit (vector)', 'audit-trail::Functional audit (vector)']
- o03 hit — What is the digital file (fascicolo di progetto) in IANUS?
  - expected: ['ianus-modular-analysis-and-implementation-plan::Modules', 'module-catalog::Modules']
  - vec best rank 8 (top score 0.64), graph hit False, merged True, seed 'ianus-modular-analysis-and-implementation-plan'
  - rerank said '1,7,6' → final: ['ianus-platform::Purpose and objectives (vector)', 'ianus-modular-analysis-and-implementation-plan::Modules (vector)', 'document-pipeline::Introduction (vector)']

## Abstention test (answers NOT in the vault)

| id | question | best vector score | delivered anyway? |
|---|---|---|---|
| x01 | What is the production SLA and uptime target? | 0.4362 | 0 passages |
| x02 | How do I configure the SMTP mail server? | 0.4198 | 0 passages |
| x03 | What are the statuses a project can have in IANUS? | 0.6315 | 3 passages |
| x04 | Who is the product owner for IANUS? | 0.6254 | 3 passages |

## Reranker contract

Replies that did not yield exactly 3 indices: ['i04', 'x01', 'x02']
Questions that returned zero final passages: ['x01', 'x02']
