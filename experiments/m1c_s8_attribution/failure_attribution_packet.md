# S8 retrieval failure attribution packet（人工审核）

协议：DECISIONS 2026-10-02 "S8 failure attribution protocol closure"。本文件由 `build_attribution_packet.py` 从冻结输入机械生成，**没有任何 AI 最终归因**。

**你只需要在 `failure_attribution_packet.csv` 里填两列**：`human_failure_tag`（初始 `PENDING_HUMAN`）与 `human_failure_note`。rank / sha / top hits 都是机械值，不需要复核。

S8 可用的 FailureTag（矩阵 A 类）：`parse_failure`、`chunk_boundary`、`bm25_miss`、`vector_miss`、`fusion_miss`。`ranking_miss` / `context_truncation` 属 packing 阶段，`generation_miss` / `refusal_miss` / `distractor_capture` 属生成阶段，本轮不用。

冻结输入：

- testset: `eval/testset_v5_3.jsonl` `05614407a0e43a7f912ae17864892b0f069a22d1ad9d1ec2bfb7362150883e8b`
- gold_chunk_map: `eval/gold_chunk_map/map__ts-v5.3__corpus-c8978777__builder-kaiva_phase_b_builder_v1.json` `8cf9f3be1b1bc296c196d1b5598c1351d456f83b1a05a6043c7b643f0fedeacc`
- corpus: `corpus/chunks.jsonl` `c89787778448d773f4fe5e00dbea328795821860412da01edda0da110425f4eb`
- bm25_analyzer: `components/retrievers/bm25.py` `11ee5029899c3c55070de9a6fbd5622eb75f3d1c3a25c05856dd9489591c61ef`
- bm25: `experiments/m1c_s8_bm25/s8_bm25_results.jsonl` `9ce4df232af8c395e0749dcb2fd9c84e5376a7939ae20af7005b12d54dac3ba8`
- vector: `experiments/m1c_s8_vector/s8_vector_results.jsonl` `0e80682cfded9fb73db0b9204120582984f33604ab5bfbc88694d47f9d371073`
- hybrid: `experiments/m1c_s8_hybrid/s8_hybrid_results.jsonl` `5d859a901f49155aa8be6f4e84f3b79bf8e564261d026f0397ef54a1cff5e9a8`

## 审核人口（机械规则）

- Tier 1：任一路 top-20 candidate miss（gold ∩ top20 = ∅），或执行手册 / prereg 明确点名的题。
- Tier 2：某一路 first_gold_rank > 5 且该路 top-20 仍有 gold（ranking diagnostic，不是自动 failure label）。

| question_id | review_tier | Tier 1 理由 | Tier 2 routes |
|---|---|---|---|
| FL08 | TIER2 | — | vector |
| FL14 | TIER1 | top20_candidate_miss:vector | hybrid |
| CN02 | TIER2 | — | bm25 |
| CN03 | TIER1 | designated:prereg §8.2：CN03_CITATION_LOGIC = ANNOTATION_CONFLICT_REQUIRES_HUMAN_REVIEW（标注冲突，不是检索失败指定） | — |
| CN04 | TIER2 | — | bm25 |
| PR01 | TIER2 | — | bm25 |
| PR03 | TIER1 | top20_candidate_miss:bm25 | hybrid |
| PR04 | TIER1 | top20_candidate_miss:bm25 | hybrid |
| CD01 | TIER1 | designated:执行手册 S8.4：CD01 的单独观察结果打出来了 | — |
| CD03 | TIER2 | — | bm25 |
| ML01 | TIER1 | top20_candidate_miss:bm25 / designated:执行手册 S8.4：多语种题检索 Recall 单独报；embedder 与生成模型的归因区分必须在 M2 之前做出 | — |
| ML02 | TIER1 | top20_candidate_miss:bm25 / designated:执行手册 S8.4：多语种题检索 Recall 单独报；embedder 与生成模型的归因区分必须在 M2 之前做出 | — |
| ML03 | TIER1 | designated:执行手册 S8.4：多语种题检索 Recall 单独报；embedder 与生成模型的归因区分必须在 M2 之前做出 | — |

---

## FL08（TIER2）

- expected / type / language：answer / fact_lookup / en
- question：How often must internal auditors undergo a refresher course?
- required_elements：["every 5 years"]
- acceptable_elements：[]
- citations：[{"doc_id": "QMM", "section": "6", "pdf_page": 57, "printed_page": "8 of 11", "quote": "internal auditors ... shall undergo a refresher course once every 5 years"}]
- query tokens（BM25 analyzer）：`how often must internal auditors undergo a refresher course`

### gold（GoldChunkMap）

**QMM:p57:1** — QMM p.57 §6；与 query 共享 token：`a auditors course internal refresher undergo`

> a. Managers are responsible for having a dialogue with their staff to identify the training needs. HODs and staff shall complete the Promotion and Career Progression Roadmap and forward to Group HR for review at the end of each year. b. Training plan for shore staff are given in QMM 6.8.2.1 (For Shore Personnel Having ISM Related Duties). c. Group HR shall review the training plan and arrange for staff to attend the relevant courses whenever they are available. d. On completion of any trainings, the staff shall submit two copies of the attendance certificate (if available) to Group HR. The Group HR staff in charge shall file the attendance certificate, update, and record in the training plan accordingly. e. Any additional trainings deemed necessary will be made known to the Group HR for updating of the original training plan. f. Company appointed internal auditors are required to undergo SMS audit courses which include ISM, ISO 9001 and 14001, prior to the appointment and shall undergo a refresher course once every 5 years. Evaluation of Training Group HR Manager and Head of Group HSEQA are responsible for establishing the methods to evaluation the effectiveness of training for shore staff. Incident Investigation Training

### 三路诊断

| route | first_gold_rank | gold_ranks | top20_candidate_miss |
|---|---|---|---|
| bm25 | 1 | [1] | False |
| vector | 7 | [7] | False |
| hybrid | 2 | [2] | False |

### bm25 top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 | ✓ | QMM:p57:1 | QMM p.57 §6 | 20.481468910714653 | 0.671931820960083 | 0.671931820960083 | a. Managers are responsible for having a dialogue with their staff to identify the training needs. HODs and staff shall complete the Promotion and Career Progression Roadmap and forward to Group HR for review at the end of each year.… |
| 2 |  | TACM:p34:1 | TACM p.34 §10 | 15.372802795404324 | 0.6058772032149613 | 0.6058772032149613 | Briefing IN-HOUSE TRAINING Shore Staff- M M M Company Security Officer (CSO) Course Shore Staff- V60 M M… |
| 3 |  | TACM:p32:1 | TACM p.32 §10 | 15.310250823627996 | 0.6049031647420636 | 0.6049031647420636 | System (ORS) Shore Staff - M M M M M M M M M M M M M Company Specific HSEQ Briefing IN-HOUSE TRAINI… |
| 4 |  | CRM:p80:1 | CRM p.80 §SF 4.3 | 14.322955993727518 | 0.5888657611114853 | 0.5888657611114853 | Security Updates How are updates managed for application? Malware Protection How is malware/virus managed? Is there an anti-malware/antivirus software? Malware Protection How often is the… |
| 5 |  | QMM:p83:0 | QMM p.83 §12 | 14.318370628295419 | 0.5887882394404915 | 0.5887882394404915 | 12.6 Internal And Third Party Auditors The selection of Auditors is the responsibility of the Designated Person and based on his recommendation, the Auditor shall be appointed by the GM/Sr.GM. Criteria The following are to be considered… |

### vector top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | QMM:p83:2 | QMM p.83 §12 | 0.6209815056374718 | 0.810490752818736 | 0.810490752818736 | Undertaken min. 6 audits and/or inspections X X X X √ Training – ISM/ISPS/MLC Internal Audit - 5 yearly* √ √ √… |
| 2 |  | QMM:p79:1 | QMM p.79 §12 | 0.6050232808697152 | 0.8025116404348576 | 0.8025116404348576 | The Manager (for Office Dept Audit) or Master / Chief Engineer (for Vessel Internal Audit) shall investigate the cause(s) of the NC and indicate the cause(s) and the proposed corrective action with the target completion date. The target dat… |
| 3 |  | QMM:p84:0 | QMM p.84 §12 | 0.6049105063161785 | 0.8024552531580893 | 0.8024552531580893 | • ISM Basic Course. • Internal Auditor Course (by a Classification Society or other certified body). The HSEQA Dept will maintain a record of all personnel who have undergone the required training and meet the above requirements for… |
| 4 |  | CRM:p57:1 | CRM p.57 §GP 1.5 | 0.6015914490318827 | 0.8007957245159414 | 0.8007957245159414 | Baseline Requirement • Vulnerability Assessment, Penetration test or similar (such as Red Team Assessment) should be conducted at least once every 2 years. It is recommended to conduct such exercise for different class o… |
| 5 |  | QMM:p73:0 | QMM p.73 §12 | 0.6001442525868571 | 0.8000721262934285 | 0.8000721262934285 | 12.1 Internal Audits and Inspections Applicable Forms: Q-9 (Internal Audit Preparation Plan Form); Q-10 (Internal Audit Report Form). Alternatively, this can be referred in the ABS NSE platform. In order to verify whether safety, qualit… |

### hybrid top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | bm25 rank | vector rank | excerpt |
|---|---|---|---|---|---|---|---|---|---|
| 1 |  | QMM:p83:2 | QMM p.83 §12 | 127/4026 | 0.9621212121212122 | 0.810490752818736 | 6 | 1 | Undertaken min. 6 audits and/or inspections X X X X √ Training – ISM/ISPS/MLC Internal Audit - 5 yearly* √ √ √… |
| 2 | ✓ | QMM:p57:1 | QMM p.57 §6 | 128/4087 | 0.9552238805970149 | 0.7947587240213021 | 1 | 7 | a. Managers are responsible for having a dialogue with their staff to identify the training needs. HODs and staff shall complete the Promotion and Career Progression Roadmap and forward to Group HR for review at the end of each year.… |
| 3 |  | QMM:p83:0 | QMM p.83 §12 | 139/4810 | 0.8813929313929314 | 0.7824180208296678 | 5 | 14 | 12.6 Internal And Third Party Auditors The selection of Auditors is the responsibility of the Designated Person and based on his recommendation, the Auditor shall be appointed by the GM/Sr.GM. Criteria The following are to be considered… |
| 4 |  | QMM:p84:0 | QMM p.84 §12 | 20/693 | 0.8802308802308803 | 0.8024552531580893 | 17 | 3 | • ISM Basic Course. • Internal Auditor Course (by a Classification Society or other certified body). The HSEQA Dept will maintain a record of all personnel who have undergone the required training and meet the above requirements for… |
| 5 |  | QMM:p57:2 | QMM p.57 §6 | 143/5110 | 0.8535225048923679 | 0.7897879350817604 | 13 | 10 | All Managers and Superintendents of the Ship Management Team are required to undergo the appropriate incident investigation and refresher trainings every 5 yearly. This training shall be supplemented whenever possible, with the practical ex… |

**human_failure_tag**：`PENDING_HUMAN`　**human_failure_note**：（在 CSV 填写）

---

## FL14（TIER1）

- expected / type / language：answer / fact_lookup / en
- question：On tankers, what oxygen content defines an atmosphere as 'inert gas'?
- required_elements：["less than 5%"]
- acceptable_elements：[]
- citations：[{"doc_id": "SMM", "section": "1", "pdf_page": 15, "printed_page": "4 of 7", "quote": "gas with low oxygen content (less than 5% by volume)"}]
- query tokens（BM25 analyzer）：`on tankers what oxygen content defines an atmosphere as inert gas`

### gold（GoldChunkMap）

**SMM:p15:3** — SMM p.15 §1；与 query 共享 token：`an as content gas inert on oxygen tankers`

> High Voltage Electrical energy that can cause serious harm to life. Normally specified for voltages >1000V. Work involving sources of ignition or at temperatures sufficiently high to cause the ignition of Hot Work flammable gases or substances. A gas which does not undergo chemical reactions under normal conditions. On tankers it is referred Inert Gas to as gas with low oxygen content (less than 5% by volume). Infrastructure The system of facilities, equipment, and services needed for the operation of the Company. Means an undesired event or a series of events that result in harm to personnel (injury / illness), Incident environmental damage, property damage / loss, or business interruption (loss of proceeds) that may have an adverse impact on the Company. The identifiable adverse physical, mental or cognitive condition of a person arising from and / or Injury and Ill Health made worse by a work activity and / or work-related situation. These adverse effects include occupational disease, illness, and death. A person or group, inside or outside the workplace, concerned with or affected by the performance Interested Parties

### 三路诊断

| route | first_gold_rank | gold_ranks | top20_candidate_miss |
|---|---|---|---|
| bm25 | 5 | [5] | False |
| vector | — | [] | True |
| hybrid | 13 | [13] | False |

### bm25 top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | SMM:p75:0 | SMM p.75 §2.16 | 26.95707688122724 | 0.7294158292838466 | 0.7294158292838466 | 2.16.5 Gas Freeing and Purging [For Tankers] Form T-51C Purging: Introduction of inert gas or Nitrogen into a tank already in inert condition with the objective of either reducing the existing oxygen and/or hydrocarbon gas content to a le… |
| 2 |  | SMM:p75:2 | SMM p.75 §2.16 | 25.37060971157691 | 0.717279400000646 | 0.717279400000646 | PPE, resuscitation and FFE must be ready for at all times. All doors, ports, windows are to be kept closed. Prior to gas freeing, a tankscope or similar instrument is used to check the hydrocarbon content (below 2% by volume) in the inert… |
| 3 |  | SMM:p94:1 | SMM p.94 §2.24 | 24.228696144686726 | 0.7078474751790309 | 0.7078474751790309 | The type of span / calibration gas used depends on the type of sensor. There are three main types of sensors: Infrared, electrotechnical and catalytic sensors. Catalytic sensors are the only sensors which rely on oxygen to function correct… |
| 4 |  | SMM:p17:2 | SMM p.17 §1 | 22.58470614989282 | 0.693107559294872 | 0.693107559294872 | Process A set of interrelated or interacting activities which transforms inputs into outputs. A space where cargo pumps, stripping pumps, ballast pumps and the piping system and valves Pump Room… |
| 5 | ✓ | SMM:p15:3 | SMM p.15 §1 | 22.163542262549086 | 0.6890889716570833 | 0.6890889716570833 | High Voltage Electrical energy that can cause serious harm to life. Normally specified for voltages >1000V. Work involving sources of ignition or at temperatures sufficiently high to cause the ignition of… |

### vector top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | SMM:p75:0 | SMM p.75 §2.16 | 0.6408205664876313 | 0.8204102832438156 | 0.8204102832438156 | 2.16.5 Gas Freeing and Purging [For Tankers] Form T-51C Purging: Introduction of inert gas or Nitrogen into a tank already in inert condition with the objective of either reducing the existing oxygen and/or hydrocarbon gas content to a le… |
| 2 |  | SMM:p75:2 | SMM p.75 §2.16 | 0.613560470278462 | 0.806780235139231 | 0.806780235139231 | PPE, resuscitation and FFE must be ready for at all times. All doors, ports, windows are to be kept closed. Prior to gas freeing, a tankscope or similar instrument is used to check the hydrocarbon content (below 2% by volume) in the inert… |
| 3 |  | SMM:p76:2 | SMM p.76 §2.16 | 0.583936905382611 | 0.7919684526913056 | 0.7919684526913056 | After cleaning, ventilating and / or gas freeing then the tank atmosphere must be sampled with all readings recorded for: • Oxygen content (≥ 20.8%). • Explosive gases (< 1% LEL). • Toxic gases (< 50% of TLV e.g., TLV for H2S < 5 p… |
| 4 |  | SMM:p72:2 | SMM p.72 §2.16 | 0.5726665746231628 | 0.7863332873115814 | 0.7863332873115814 | • Which has been closed for a length of time. • Which has inert gas. • Which has not been adequately ventilated. • Which is adjacent or connected to a space that is normally inerted. • Which has had CO2 injected into it to ex… |
| 5 |  | SMM:p74:1 | SMM p.74 §2.16 | 0.553997452390067 | 0.7769987261950335 | 0.7769987261950335 | [For Tankers] Prior entry into an enclosed space, the space shall be made free of any contaminants that it may contain which may give off harmful gases or cause lack of oxygen. This shall be done by washing and gas freeing, or gas freeing o… |

### hybrid top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | bm25 rank | vector rank | excerpt |
|---|---|---|---|---|---|---|---|---|---|
| 1 |  | SMM:p75:0 | SMM p.75 §2.16 | 2/61 | 1.0 | 0.8204102832438156 | 1 | 1 | 2.16.5 Gas Freeing and Purging [For Tankers] Form T-51C Purging: Introduction of inert gas or Nitrogen into a tank already in inert condition with the objective of either reducing the existing oxygen and/or hydrocarbon gas content to a le… |
| 2 |  | SMM:p75:2 | SMM p.75 §2.16 | 1/31 | 0.9838709677419355 | 0.806780235139231 | 2 | 2 | PPE, resuscitation and FFE must be ready for at all times. All doors, ports, windows are to be kept closed. Prior to gas freeing, a tankscope or similar instrument is used to check the hydrocarbon content (below 2% by volume) in the inert… |
| 3 |  | SMM:p17:2 | SMM p.17 §1 | 65/2112 | 0.9386837121212122 | 0.7750134059916287 | 4 | 6 | Process A set of interrelated or interacting activities which transforms inputs into outputs. A space where cargo pumps, stripping pumps, ballast pumps and the piping system and valves Pump Room… |
| 4 |  | SMM:p94:1 | SMM p.94 §2.24 | 131/4284 | 0.93265639589169 | 0.7700296612558162 | 3 | 8 | The type of span / calibration gas used depends on the type of sensor. There are three main types of sensors: Infrared, electrotechnical and catalytic sensors. Catalytic sensors are the only sensors which rely on oxygen to function correct… |
| 5 |  | SMM:p72:2 | SMM p.72 §2.16 | 131/4288 | 0.9317863805970149 | 0.7863332873115814 | 7 | 4 | • Which has been closed for a length of time. • Which has inert gas. • Which has not been adequately ventilated. • Which is adjacent or connected to a space that is normally inerted. • Which has had CO2 injected into it to ex… |

**human_failure_tag**：`PENDING_HUMAN`　**human_failure_note**：（在 CSV 填写）

---

## CN02（TIER2）

- expected / type / language：answer / concept / en
- question：What is a Risk Assessment, in the context of the safety management system?
- required_elements：["safety management tool", "safety culture / manage risk"]
- acceptable_elements：[]
- citations：[{"doc_id": "SMM", "section": "2.1", "pdf_page": 20, "printed_page": "1 of 12", "quote": "Risk Assessment is a safety management tool which can be used to enhance the ‘Safety Culture’ in an organization"}]
- query tokens（BM25 analyzer）：`what is a risk assessment in the context of the safety management system`

### gold（GoldChunkMap）

**SMM:p20:0** — SMM p.20 §2.1；与 query 共享 token：`a assessment in is management of risk safety the`

> Applicable Forms: Q-14 (Risk Assessment Form); Q-25 (Daily Work Planner Form). 2.1.1 Risk Assessment Risk Assessment is a safety management tool which can be used to enhance the ‘Safety Culture’ in an organization. Risk is a measure of the likelihood / probability that an undesirable scenario will occur and the resulting consequences. During their various work activities, ship staff are exposed to different types of hazards which could also result in hazardous or potentially hazardous situations. These pose a certain level or degree of safety and health risk, which should be reduced. When changes are made to documents describing processes or procedures, a risk assessment shall be made to assess the immediate impact of such changes and the secondary risks associated with any later residual fall-out of the changes. 2.1.2 Process of Formal Risk Assessment All Risk Assessments shall be carried out using the ABS RA platform. Alternatively, Form Q-14 shall be used for carrying out formal risk assessments. Step 1: Identify Hazards and Existing Preventive Measures The risk assessment process for any work activity begins by first identifying all its hazards and documenting all existing preventive measures that can be put in place or can be practiced for controlling each of the identified hazards.

### 三路诊断

| route | first_gold_rank | gold_ranks | top20_candidate_miss |
|---|---|---|---|
| bm25 | 7 | [7] | False |
| vector | 1 | [1] | False |
| hybrid | 3 | [3] | False |

### bm25 top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | QMM:p1:0 | QMM p.1 §Part I | 20.50274097921642 | 0.6721606098673665 | 0.6721606098673665 | 1 GENERAL 1.1 Authorization and Scope 1.2 Scope of Management System 1.3 Application 1.4 Distribution 1.5 Objectives, Vision and Mission and their Implementation 1.6 General Requirements 1.7… |
| 2 |  | QMM:p14:0 | QMM p.14 §1 | 19.26792384590027 | 0.6583290276190615 | 0.6583290276190615 | 1.8 Management System Company has established, implemented, and maintains a management system to achieve all objectives and targets, taking into account of the operating requirements of each ship type in compliance to applicable regulation… |
| 3 |  | QMM:p97:0 | QMM p.97 §14 | 18.94536490874463 | 0.6545215432064247 | 0.6545215432064247 | 14.1 Safety and Environmental Management Planning In the planning for Quality, Occupational Health, Safety and Environmental management, Company determines the relevant internal and external issues and identifies the interested parties rel… |
| 4 |  | SMM:p21:0 | SMM p.21 §2.1 | 18.80777557112283 | 0.6528714973042178 | 0.6528714973042178 | 2.1.3 Conducting a Risk Assessment The ‘Risk Assessment’ exercise for a particular ‘Activity or Action’ is a process that utilises the collective knowledge and experience of all participants in ‘brainstorming’ through the following steps:… |
| 5 |  | SMM:p40:0 | SMM p.40 §2.5 | 17.969084578707214 | 0.6424623776348772 | 0.6424623776348772 | Step-4 Debriefing Person in charge of the work activity shall conduct a debriefing after completion of the work activity undertaken. A debriefing should encompass the following: 1. Discussing what made the job successful. 2. Di… |

### vector top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 | ✓ | SMM:p20:0 | SMM p.20 §2.1 | 0.7334385861409921 | 0.8667192930704961 | 0.8667192930704961 | Applicable Forms: Q-14 (Risk Assessment Form); Q-25 (Daily Work Planner Form). 2.1.1 Risk Assessment Risk Assessment is a safety management tool which can be used to enhance the ‘Safety Culture’ in an organization. Risk is a measure of… |
| 2 |  | SMM:p21:0 | SMM p.21 §2.1 | 0.6821524375607283 | 0.8410762187803642 | 0.8410762187803642 | 2.1.3 Conducting a Risk Assessment The ‘Risk Assessment’ exercise for a particular ‘Activity or Action’ is a process that utilises the collective knowledge and experience of all participants in ‘brainstorming’ through the following steps:… |
| 3 |  | SMM:p1:0 | SMM p.1 §PART I | 0.6696404366725224 | 0.8348202183362612 | 0.8348202183362612 | 1 GENERAL 1.1 Authorisation and Scope 1.2 Distribution 1.3 Safety Management System (SMS) Definitions and Glossary of Terms 2 SHIPBOARD OPERATIONS 2.1 Hazard Identification and… |
| 4 |  | QMM:p97:0 | QMM p.97 §14 | 0.6562990650604678 | 0.8281495325302339 | 0.8281495325302339 | 14.1 Safety and Environmental Management Planning In the planning for Quality, Occupational Health, Safety and Environmental management, Company determines the relevant internal and external issues and identifies the interested parties rel… |
| 5 |  | SMM:p20:1 | SMM p.20 §2.1 | 0.647185800289274 | 0.8235929001446369 | 0.8235929001446369 | Step 2: Determine Likelihood and Severity Each of the identified hazards is considered from the aspect of ‘Likelihood / Probability’ of occurrence and, the severity of the ‘Consequence’. Both elements are assessed separately, considering… |

### hybrid top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | bm25 rank | vector rank | excerpt |
|---|---|---|---|---|---|---|---|---|---|
| 1 |  | SMM:p21:0 | SMM p.21 §2.1 | 63/1984 | 0.9684979838709677 | 0.8410762187803642 | 4 | 2 | 2.1.3 Conducting a Risk Assessment The ‘Risk Assessment’ exercise for a particular ‘Activity or Action’ is a process that utilises the collective knowledge and experience of all participants in ‘brainstorming’ through the following steps:… |
| 2 |  | QMM:p97:0 | QMM p.97 §14 | 127/4032 | 0.9606894841269841 | 0.8281495325302339 | 3 | 4 | 14.1 Safety and Environmental Management Planning In the planning for Quality, Occupational Health, Safety and Environmental management, Company determines the relevant internal and external issues and identifies the interested parties rel… |
| 3 | ✓ | SMM:p20:0 | SMM p.20 §2.1 | 128/4087 | 0.9552238805970149 | 0.8667192930704961 | 7 | 1 | Applicable Forms: Q-14 (Risk Assessment Form); Q-25 (Daily Work Planner Form). 2.1.1 Risk Assessment Risk Assessment is a safety management tool which can be used to enhance the ‘Safety Culture’ in an organization. Risk is a measure of… |
| 4 |  | SMM:p1:0 | SMM p.1 §PART I | 43/1386 | 0.9462481962481962 | 0.8348202183362612 | 6 | 3 | 1 GENERAL 1.1 Authorisation and Scope 1.2 Distribution 1.3 Safety Management System (SMS) Definitions and Glossary of Terms 2 SHIPBOARD OPERATIONS 2.1 Hazard Identification and… |
| 5 |  | SMM:p27:0 | SMM p.27 §2.1 | 139/4824 | 0.8788349917081261 | 0.8204458531783623 | 12 | 7 | 2.1.7 Risk Assessment Exercises The purpose of Risk Assessment (RA) Exercises is primarily to afford maximum opportunity to all ship staff to participate in and gain experience in the conduct of ‘Risk Assessment’ onboard. All staff are enc… |

**human_failure_tag**：`PENDING_HUMAN`　**human_failure_note**：（在 CSV 填写）

---

## CN03（TIER1）

- expected / type / language：answer / concept / en
- question：What is the role of the DPA when an emergency occurs onboard?
- required_elements：["overall management of the emergency response", "main contact person ashore"]
- acceptable_elements：["lead role in the Office's Emergency Response Team", "ADPA acts if DPA unavailable", "notified for all emergencies"]
- citations：[{"doc_id": "ERM", "section": "4.1", "pdf_page": 14, "printed_page": "2 of 9", "quote": "The DPA is responsible for the overall management of the Emergency response and act as the main contact person ashore for the Emergency response"}, {"doc_id": "QMM", "section": "4", "pdf_page": 46, "printed_page": "1 of 2", "quote": "Participating in a lead role in the Emergency Response Team of the Office"}]
- query tokens（BM25 analyzer）：`what is the role of the dpa when an emergency occurs onboard`

### gold（GoldChunkMap）

**ERM:p14:0** — ERM p.14 §4.1；与 query 共享 token：`an dpa emergency is of the`

> 4.1.2 Line of Communication The DPA is responsible for the overall management of the Emergency response and act as the main contact person ashore for the Emergency response. In the event the DPA is not available, the ADPA shall act in the capacity as the DPA. In an event of an Emergency involving a Group owned ship, the Master is fully in-charge of all shipboard operations. The Master’s priority is the safety of personnel and Group owned vessel and to take all necessary actions to prevent the escalation of the Emergency. An immediate initial verbal notification to the DPA must be initiated by the Master at the earliest opportunity (no later than 30 minutes of first becoming aware of the situation) in order to enable the DPA to assist the vessel in handling the Emergency. The DPA must be notified at first instance for all Emergencies. Thereafter, the DPA shall inform, depending on type and level of emergency, by telephone: a. GM; b. Head of Operation; c. Insurance Department; d. Head of Human Resources, if the Emergency is particular to the safety of shore based employees; e. Head of Crewing (if the Emergency is particular to safety of Seafarer); f. Head of Technical (if the Emergency is particular to hull, machinery etc); g. Marine Manager.

**QMM:p46:1** — QMM p.46 §4；与 query 共享 token：`emergency of onboard role the`

> His inter-relationships: Reports to: Fleet Director / Sr. GM Liaises with: Heads of All Departments ashore and with the Masters onboard. Contactable by: All Ships’ Crew. His responsibilities:  Being familiar with and control the content and changes to the Safety Management System (SMS) Documentation.  Ensuring proper distribution of the Manuals.  Performing familiarization of staff with the contents of the SMS.  Arranging internal ISM / ISPS audits of ships and office at annual intervals, studying the results, and ensuring that any non-conformities (NCs) are properly closed.  Arranging external ISM / ISPS audits of ships and office at prescribed intervals, studying the results, ensuring that any NCs are properly closed, and that Certificates are duly endorsed or renewed after the audit.  Receiving and responding to Reviews from the Masters (along with other department heads).  Receiving and responding to Safety Meeting Reports from ships.  Arranging the Management Reviews ashore and following up on the action points.  Reading Non-Conformity Reports (NCRs) from ships and monitors the corrective and preventive action.  Participating in a lead role in the Emergency Response Team of the Office.  Reading of emergency drill reports from ships and ensuring that they are properly complied with at the specified intervals.

### 三路诊断

| route | first_gold_rank | gold_ranks | top20_candidate_miss |
|---|---|---|---|
| bm25 | 2 | [2] | False |
| vector | 1 | [1] | False |
| hybrid | 1 | [1] | False |

### bm25 top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | QMM:p47:0 | QMM p.47 §4 | 18.584432564313722 | 0.6501592264425596 | 0.6501592264425596 | If any staff onboard find that avenues of communication to superiors are closed to their concerns on safety, health, and environmental matters, they have a right to contact and communicate such matters directly to the DPA through the contac… |
| 2 | ✓ | ERM:p14:0 | ERM p.14 §4.1 | 15.071223891579994 | 0.6011363448691296 | 0.6011363448691296 | 4.1.2 Line of Communication The DPA is responsible for the overall management of the Emergency response and act as the main contact person ashore for the Emergency response. In the event the DPA is not available, the ADPA shall act in the… |
| 3 |  | ERM:p33:1 | ERM p.33 §6 | 15.003108253636654 | 0.6000497258757611 | 0.6000497258757611 | • The Head of Marine or alternate DPA in his absence would assume this role • Advice on navigational emergencies. • Advice on emergencies related to marine pollution. • Advice on emergencies related to cargo carried on-boar… |
| 4 |  | ERM:p105:0 | ERM p.105 §B.19 | 14.203930902343087 | 0.586843970082895 | 0.586843970082895 | Entry into an enclosed space i.e., cargo tank, cofferdam, double bottom, or similar enclosed spaces shall not be permitted without the permission from a responsible officer who is satisfied that the atmosphere within is safe in all respects… |
| 5 |  | ERM:p67:0 | ERM p.67 §13 | 13.884056885068278 | 0.5813106605749314 | 0.5813106605749314 | 13.5.3 Crew Accident Onboard Master is to report to the Company whenever an accident occurs onboard the vessel and include the following information:  Particulars of injured person.  Date / Time of accident.  Place of accident. … |

### vector top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 | ✓ | ERM:p14:0 | ERM p.14 §4.1 | 0.7143211620137213 | 0.8571605810068607 | 0.8571605810068607 | 4.1.2 Line of Communication The DPA is responsible for the overall management of the Emergency response and act as the main contact person ashore for the Emergency response. In the event the DPA is not available, the ADPA shall act in the… |
| 2 |  | QMM:p47:0 | QMM p.47 §4 | 0.6617666040232294 | 0.8308833020116146 | 0.8308833020116146 | If any staff onboard find that avenues of communication to superiors are closed to their concerns on safety, health, and environmental matters, they have a right to contact and communicate such matters directly to the DPA through the contac… |
| 3 |  | ERM:p34:3 | ERM p.34 §6 | 0.659082334991206 | 0.829541167495603 | 0.829541167495603 | DPA Will communicate with the vessel on To ensure prompt and correct (Alternate: Alt DPA / HSEQA) safety and environmental issues. information is given to interested… |
| 4 |  | CMM:p87:0 | CMM p.87 §Appendix II | 0.6500878648568438 | 0.8250439324284219 | 0.8250439324284219 | Appendix II – Onboard Crew Personnel Responsibilities Refer to Appendix VI for the flow chart of responsibilities of personnel onboard Master Master is the Owner’s Representative onboard and is responsible for overall management of the shi… |
| 5 |  | ERM:p124:3 | ERM p.124 §D.1 | 0.641980686918044 | 0.820990343459022 | 0.820990343459022 | owners & cargo interests. To ensure prompt and correct DPA Will communicate with the vessel on information is given to interested (Alternate: Alt DPA / HSEQA) safety and environmental… |

### hybrid top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | bm25 rank | vector rank | excerpt |
|---|---|---|---|---|---|---|---|---|---|
| 1 | ✓ | ERM:p14:0 | ERM p.14 §4.1 | 123/3782 | 0.9919354838709677 | 0.8571605810068607 | 2 | 1 | 4.1.2 Line of Communication The DPA is responsible for the overall management of the Emergency response and act as the main contact person ashore for the Emergency response. In the event the DPA is not available, the ADPA shall act in the… |
| 2 |  | QMM:p47:0 | QMM p.47 §4 | 123/3782 | 0.9919354838709677 | 0.8308833020116146 | 1 | 2 | If any staff onboard find that avenues of communication to superiors are closed to their concerns on safety, health, and environmental matters, they have a right to contact and communicate such matters directly to the DPA through the contac… |
| 3 |  | ERM:p33:1 | ERM p.33 §6 | 137/4662 | 0.8962891462891462 | 0.7935038083128092 | 3 | 14 | • The Head of Marine or alternate DPA in his absence would assume this role • Advice on navigational emergencies. • Advice on emergencies related to marine pollution. • Advice on emergencies related to cargo carried on-boar… |
| 4 |  | ERM:p55:0 | ERM p.55 §11 | 29/1050 | 0.8423809523809523 | 0.8052409305486397 | 15 | 10 | DPA shall prepare an annual emergency exercise planner and notify all members in advance prior conducting an exercise. ERM/D.13 - Exercise Plan (Section D) shall be used. All communication announcing a drill shall be prefixed with the wor… |
| 5 |  | ERM:p13:0 | ERM p.13 §4.1 | 37/1368 | 0.8249269005847953 | 0.7969612161714065 | 16 | 12 | 4.1.1 Abbreviations ADPA Alternate Designated Person Ashore ACSO Alternate Company Security Officer CEO Chief Operating Officer, Pacific Carriers Limited CFO Chief Financ… |

**human_failure_tag**：`PENDING_HUMAN`　**human_failure_note**：（在 CSV 填写）

---

## CN04（TIER2）

- expected / type / language：answer / concept / en
- question：What is the purpose of a toolbox meeting before a job?
- required_elements：["briefed on task & responsibilities", "understand methods and tools", "understand the hazards", "understand the safety/control measures", "clear doubts / speak up to improve safety"]
- acceptable_elements：[]
- citations：[{"doc_id": "SMM", "section": "2.5", "pdf_page": 38, "printed_page": "1 of 3", "quote": "personnel engaged on a task are ... Briefed on the task to be undertaken ... Understand the methods to be employed ... Understand the hazards associated with the task ... Understand the safety measures that will be in place ... Clear doubts and speak up on ideas"}]
- query tokens（BM25 analyzer）：`what is the purpose of a toolbox meeting before a job`

### gold（GoldChunkMap）

**SMM:p38:0** — SMM p.38 §2.5；与 query 共享 token：`a is meeting of the toolbox`

> Applicable Form: Q-25 (Daily Work Planner and Toolbox Meeting). Step-2 Toolbox Meeting The toolbox meetings are held to ensure that all personnel engaged on a task are: • Briefed on the task to be undertaken including the assignment of responsibilities. • Understand the methods to be employed and the tools to be used. • Understand the hazards associated with the task(s). • Understand the safety measures that will be in place to control the identified hazards. • Clear doubts and speak up on ideas they may have to improve safety. Risk Assessments associated with the respective work activities should be reviewed / sent for office approval as indicated on form Q25. Person in charge of the work activity should be appointed to give a Toolbox talk and debriefing post completion of the work activity. All the personnel participating in the work activity to attend the meeting and their names/ ranks/ signatures shall be included in Part B of form Q-25. For certain work activities that may be repetitive over a relatively short period of time, daily work planner and toolbox meeting need not be conducted prior to each occasion, so long as hazards remain unchanged. Only Toolbox Talk is required.

### 三路诊断

| route | first_gold_rank | gold_ranks | top20_candidate_miss |
|---|---|---|---|
| bm25 | 9 | [9] | False |
| vector | 1 | [1] | False |
| hybrid | 4 | [4] | False |

### bm25 top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | SMM:p43:1 | SMM p.43 §2.7 | 20.559556473087042 | 0.6727701199195504 | 0.6727701199195504 | Before resuming work, the person in charge shall check the job site to ensure that it is safe to continue. CHECK IF IT IS SAFE It shall also be checked that the correct… |
| 2 |  | SMM:p64:1 | SMM p.64 §2.14 | 20.416463642194483 | 0.6712306822503932 | 0.6712306822503932 | • Inspect the work area to ensure all tools and items have been removed. • Confirm that all personnel are safely located away from the hazardous areas. • Verify that controls are in neutral positions. • Remove unrequired devices and… |
| 3 |  | SMM:p86:2 | SMM p.86 §2.20 | 18.849733701127047 | 0.653376349896452 | 0.653376349896452 |  Include a decision matrix to establish approval levels for varying scenarios. Decision Making and 4.  Identifies SIMOPS that require approval from the office. App… |
| 4 |  | SMM:p85:0 | SMM p.85 §2.19 | 18.78213880146005 | 0.6525623036918742 | 0.6525623036918742 | Completion of Cold Work: • On completion and prior to standing down, it shall be ascertained that the work has had the desired effect. • Lockouts-Tagouts shall be only removed by the responsible person. • All warning signs shall be r… |
| 5 |  | SMM:p37:0 | SMM p.37 §2.4 | 18.77145008302696 | 0.652433229081517 | 0.652433229081517 | Applicable Form: Q-25 (Daily Work Planner and Toolbox Meeting). The daily work planner and toolbox meeting provides an opportunity for personnel involved to contribute to the process both on technical and safety issues, which is held prior… |

### vector top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 | ✓ | SMM:p38:0 | SMM p.38 §2.5 | 0.7085644075138544 | 0.8542822037569272 | 0.8542822037569272 | Applicable Form: Q-25 (Daily Work Planner and Toolbox Meeting). Step-2 Toolbox Meeting The toolbox meetings are held to ensure that all personnel engaged on a task are: • Briefed on the task to be undertaken including the assignmen… |
| 2 |  | SMM:p39:0 | SMM p.39 §2.5 | 0.6672579009733891 | 0.8336289504866945 | 0.8336289504866945 | Step- 3 Toolbox Talk Person appointed to give a toolbox talk shall conduct a toolbox talk prior to commencing the work activity. A toolbox talk should encompass the following: 1. Making the team aware of the hazards and the control m… |
| 3 |  | SMM:p37:0 | SMM p.37 §2.4 | 0.6585983496608956 | 0.8292991748304478 | 0.8292991748304478 | Applicable Form: Q-25 (Daily Work Planner and Toolbox Meeting). The daily work planner and toolbox meeting provides an opportunity for personnel involved to contribute to the process both on technical and safety issues, which is held prior… |
| 4 |  | SMM:p86:2 | SMM p.86 §2.20 | 0.6117857037141204 | 0.8058928518570603 | 0.8058928518570603 |  Include a decision matrix to establish approval levels for varying scenarios. Decision Making and 4.  Identifies SIMOPS that require approval from the office. App… |
| 5 |  | SMM:p43:1 | SMM p.43 §2.7 | 0.593828804478412 | 0.7969144022392061 | 0.7969144022392061 | Before resuming work, the person in charge shall check the job site to ensure that it is safe to continue. CHECK IF IT IS SAFE It shall also be checked that the correct… |

### hybrid top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | bm25 rank | vector rank | excerpt |
|---|---|---|---|---|---|---|---|---|---|
| 1 |  | SMM:p43:1 | SMM p.43 §2.7 | 126/3965 | 0.9692307692307692 | 0.7969144022392061 | 1 | 5 | Before resuming work, the person in charge shall check the job site to ensure that it is safe to continue. CHECK IF IT IS SAFE It shall also be checked that the correct… |
| 2 |  | SMM:p86:2 | SMM p.86 §2.20 | 127/4032 | 0.9606894841269841 | 0.8058928518570603 | 3 | 4 |  Include a decision matrix to establish approval levels for varying scenarios. Decision Making and 4.  Identifies SIMOPS that require approval from the office. App… |
| 3 |  | SMM:p37:0 | SMM p.37 §2.4 | 128/4095 | 0.9533577533577534 | 0.8292991748304478 | 5 | 3 | Applicable Form: Q-25 (Daily Work Planner and Toolbox Meeting). The daily work planner and toolbox meeting provides an opportunity for personnel involved to contribute to the process both on technical and safety issues, which is held prior… |
| 4 | ✓ | SMM:p38:0 | SMM p.38 §2.5 | 130/4209 | 0.9420289855072463 | 0.8542822037569272 | 9 | 1 | Applicable Form: Q-25 (Daily Work Planner and Toolbox Meeting). Step-2 Toolbox Meeting The toolbox meetings are held to ensure that all personnel engaged on a task are: • Briefed on the task to be undertaken including the assignmen… |
| 5 |  | SMM:p64:1 | SMM p.64 §2.14 | 67/2232 | 0.9155465949820788 | 0.7527716489163344 | 2 | 12 | • Inspect the work area to ensure all tools and items have been removed. • Confirm that all personnel are safely located away from the hazardous areas. • Verify that controls are in neutral positions. • Remove unrequired devices and… |

**human_failure_tag**：`PENDING_HUMAN`　**human_failure_note**：（在 CSV 填写）

---

## PR01（TIER2）

- expected / type / language：answer / procedure / en
- question：What immediate actions must be taken in the event of a man overboard?
- required_elements：["inform OOW and Master", "revert to manual steering, keep propeller clear", "release MOB marker/SART", "press MOB/Mark-Position on GPS and ECDIS", "three prolonged blasts", "General Emergency Alarm", "commence Williamson turn", "engines on standby, do NOT use M/E emergency stop", "hoist signal flag 'O'", "prepare rescue boat"]
- acceptable_elements：["additional lookouts / search lights at night", "manoeuvre to rescue or search per IAMSAR", "distribute portable VHF radios", "rig pilot ladder/nets or lower a survival-suit crew member", "create a lee when approaching", "hypothermia precautions", "seated/deck-chair hoist to avoid suspension trauma", "further coordination with third parties after rescue", "recover the MOB marker/SART", "record all actions in the Log Book", "preserve the VDR recording", "switch off Wi-Fi and crew internet (Social Media Policy)", "conduct alcohol test for all crew", "collect urine samples for drug test if Severity Level 3+"]
- citations：[{"doc_id": "ERM", "section": "B.17", "pdf_page": 103, "printed_page": "1 of 1", "quote": "Inform the Officer of the Watch and Master ... commence Williamson turn ... place the engines on standby ... Hoist signal flag ... Switch off Wi-Fi and crew internet"}]
- query tokens（BM25 analyzer）：`what immediate actions must be taken in the event of a man overboard`

### gold（GoldChunkMap）

**ERM:p103:1** — ERM p.103 §B.17；与 query 共享 token：`a in man of overboard the`

> • Inform the Officer of the Watch and Master if they are not already aware of the situation. • Revert to manual steering and manoeuvre the vessel to keep the propeller away from the side on which the man has gone overboard. • Release MOB marker and SART to the side of man overboard or men sighted. • Press the Man Overboard or Mark Position button on the GPS and ECDIS. • Sound the MOB sound signal (three prolonged blasts on the ship’s whistle). • Sound the General Emergency Alarm and inform crew of Man overboard port / stbd side / rescue boat stations over PA. • Reduce vessel speed and commence Williamson turn. • Additional lookouts posted to keep constant watch for the man overboard or men in the water. If at night, search lights operated without interfering with safe navigation. • Inform the Engineer of the Watch and place the engines on standby (Do not use the M/E Emcy Stop). • Manoeuvre the vessel to rescue the man overboard or carry out a search as given in IAMSAR. • Hoist signal flag ‘O’. • Prepare rescue boat for launching and rescue equipment in accordance with ship specific plan “Rescue of Person from Water”. • Distribute portable VHF radios for communication.

**ERM:p103:2** — ERM p.103 §B.17；与 query 共享 token：`a actions in man of taken the`

> • Rig pilot ladder / nets to assist in the recovery, or lower survival suit-clad crew member with rescue net from ship’s pre-identified rescue point. • Manoeuvre the vessel to create a lee when approaching the man in water. • If man recovered and suffering from hypothermia take all suitable precautions to insulate him before bringing him into the accommodation and follow hypothermia recovery procedure. • If man is being hoisted by rescue harness, ensure hoisted person is in deck chair position, and not vertical, to avoid suspension trauma. • Further coordination with third parties after persons in water rescued. • If possible, recover the MOB marker and SART. • Record all actions taken in the Log Book. • Preserve VDR recording. • Switch off Wi-Fi and crew internet. Comply with Company’s Social Media Policy. • Conduct Alcohol Test for all crew and record data. • Collect urine samples of all crew for Drug Test (if incident actual Severity Level 3 and above), sample to offload for shore lab test.

### 三路诊断

| route | first_gold_rank | gold_ranks | top20_candidate_miss |
|---|---|---|---|
| bm25 | 19 | [19] | False |
| vector | 4 | [4, 12] | False |
| hybrid | 4 | [4] | False |

### bm25 top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | ERM:p103:0 | ERM p.103 §B.17 | 29.585056602023062 | 0.7473794189424267 | 0.7473794189424267 | In the event of man overboard, or sighting of persons in the water needing rescue, the action taken should include but shall not limited to the following: (Note: The IMO - International Aeronautical and Maritime Search and Rescue Manual - I… |
| 2 |  | ERM:p104:0 | ERM p.104 §B.18 | 22.18534965749997 | 0.6892996314654063 | 0.6892996314654063 | In the event a crew member is found missing onboard while at sea, actions should be taken, but not limited to the following: IMMEDIATE ACTIONS:… |
| 3 |  | ERM:p86:0 | ERM p.86 §B.5 | 22.169731662463686 | 0.6891487903932935 | 0.6891487903932935 | In the event of a collision or allision, action taken should include but not be limited to the following: IMMEDIATE ACTIONS:… |
| 4 |  | ERM:p93:0 | ERM p.93 §B.10 | 20.63223229669672 | 0.6735464819167499 | 0.6735464819167499 | In the event of failure of the main engine (except in open and clear waters with no traffic) action should be taken not limited to: IMMEDIATE ACTIONS:… |
| 5 |  | ERM:p106:0 | ERM p.106 §B.20 | 20.502565932497536 | 0.6721587284777912 | 0.6721587284777912 | In the event of serious personnel injury or sickness that requires immediate medical assistance, the action taken should include, but are not limited to the following: IMMEDIATE ACTIONS:… |

### vector top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | ERM:p103:0 | ERM p.103 §B.17 | 0.7363412149064724 | 0.8681706074532363 | 0.8681706074532363 | In the event of man overboard, or sighting of persons in the water needing rescue, the action taken should include but shall not limited to the following: (Note: The IMO - International Aeronautical and Maritime Search and Rescue Manual - I… |
| 2 |  | ERM:p85:0 | ERM p.85 §B.4 | 0.6854440314166457 | 0.8427220157083228 | 0.8427220157083228 | In the event of breakaway action taken should include but not be limited to the following: IMMEDIATE ACTIONS: • Raise the alarm. • Shut down cargo transfer. • Detach cargo… |
| 3 |  | ERM:p104:0 | ERM p.104 §B.18 | 0.6829216377423031 | 0.8414608188711515 | 0.8414608188711515 | In the event a crew member is found missing onboard while at sea, actions should be taken, but not limited to the following: IMMEDIATE ACTIONS:… |
| 4 | ✓ | ERM:p103:1 | ERM p.103 §B.17 | 0.6730896360106526 | 0.8365448180053263 | 0.8365448180053263 | • Inform the Officer of the Watch and Master if they are not already aware of the situation. • Revert to manual steering and manoeuvre the vessel to keep the propeller away from the side on which the man has gone overbo… |
| 5 |  | ERM:p107:0 | ERM p.107 §B.20 | 0.6725734288399257 | 0.8362867144199628 | 0.8362867144199628 | If evacuation of the injured crew by boat from shore or to other vessels is needed: IMMEDIATE ACTIONS: • Establish communication with other vessel to coordinate course and speed, ETA.… |

### hybrid top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | bm25 rank | vector rank | excerpt |
|---|---|---|---|---|---|---|---|---|---|
| 1 |  | ERM:p103:0 | ERM p.103 §B.17 | 2/61 | 1.0 | 0.8681706074532363 | 1 | 1 | In the event of man overboard, or sighting of persons in the water needing rescue, the action taken should include but shall not limited to the following: (Note: The IMO - International Aeronautical and Maritime Search and Rescue Manual - I… |
| 2 |  | ERM:p104:0 | ERM p.104 §B.18 | 125/3906 | 0.9760624679979518 | 0.8414608188711515 | 2 | 3 | In the event a crew member is found missing onboard while at sea, actions should be taken, but not limited to the following: IMMEDIATE ACTIONS:… |
| 3 |  | EMM:p74:0 | EMM p.74 §6 | 35/1224 | 0.872140522875817 | 0.8314123205693299 | 12 | 8 | 6.10 Immediate Actions – Emergencies Onboard Reference Section: Emergency Response Manual (ERM) Section 5.3. Once an emergency has been decided upon, following immediate action is to be initiated: Seven… |
| 4 | ✓ | ERM:p103:1 | ERM p.103 §B.17 | 143/5056 | 0.8626384493670886 | 0.8365448180053263 | 19 | 4 | • Inform the Officer of the Watch and Master if they are not already aware of the situation. • Revert to manual steering and manoeuvre the vessel to keep the propeller away from the side on which the man has gone overbo… |
| 5 |  | ERM:p98:0 | ERM p.98 §B.13 | 143/5110 | 0.8535225048923679 | 0.8268390810523907 | 13 | 10 | Note: This section to be referred to in the event of failure of a system classed as ‘critical’ onboard. IMMEDIATE ACTIONS:  Determine the effect of the failure on the ship.  Dis… |

**human_failure_tag**：`PENDING_HUMAN`　**human_failure_note**：（在 CSV 填写）

---

## PR03（TIER1）

- expected / type / language：answer / procedure / en
- question：What is the procedure for a seafarer to raise and escalate a grievance?
- required_elements：["address to HOD/superior officer", "HOD resolves preferably within 5 days", "refer to Master if unresolved", "lodge complaint to the Crewing Manager if unsatisfied with Master", "resolved within 8 days once received ashore", "if against the Master, approach the DPA/Crewing Manager", "right to be accompanied/represented"]
- acceptable_elements：["complaints and decisions recorded onboard, copy to seafarer", "right to file directly with Master/owner/competent authorities", "complainant's rights protected / not prejudiced", "may bypass the flow and approach Master/DPA/authority directly", "C/O and C/E provide impartial advice"]
- citations：[{"doc_id": "CMM", "section": "12", "pdf_page": 74, "printed_page": "74 of 133", "quote": "All complaints should be addressed to the Head of the Department ... preferably within a time limit not exceeding 5 days ... may refer it to the master ... wishes to lodge a complaint to the Crewing Manager ... resolved within 8 days ... the complaint is against the Master, the employee is encouraged to approach the DPA/Crewing Manager ... right to be accompanied"}]
- query tokens（BM25 analyzer）：`what is the procedure for a seafarer to raise and escalate a grievance`

### gold（GoldChunkMap）

**CMM:p74:1** — CMM p.74 §12；与 query 共享 token：`a and is seafarer the to`

> 1. All complaints should be addressed to the Head of the Department of the Seafarer lodging the complaint or to the Seafarer’s superior officer. 2. The Head of Department or superior officer should then attempt to resolve the matter as soon as the service of the ship permits, preferably within a time limit not exceeding 5 days and appropriate to the seriousness of the issues involved. 3. If the head of department or superior officer cannot resolve the complaint to the satisfaction of the Seafarer, the latter may refer it to the master, who should handle the matter personally. 4. Seafarer should always have the right to be accompanied and to be represented by another Seafarer of their choice on board the ship concerned. 5. All complaints and the decisions concerning them should be recorded onboard and a copy provided to the Seafarer concerned. 6. If a Seafarer is not satisfied with the action taken by the Master because of the master’s investigation, or by the master’s failure to take any action, the seafarer may state his or her dissatisfaction to the Master and indicate that he or she wishes to lodge a complaint to the Crewing Manager.

**CMM:p74:2** — CMM p.74 §12；与 query 共享 token：`a and for is seafarer the to`

> 7. Once the complaint is received ashore, it will need to be resolved within 8 days, and appropriate to the seriousness of the issues involved. Where appropriate consultation to be held with the Seafarer concerned or any person they may appoint as their representative. 8. For cases where the complaint is against the Master, the employee is encouraged to approach the DPA/Crewing Manager. 9. In all cases Seafarer should have a right to file their complaints directly with the master, the vessel owner, and competent authorities. Master, on request, shall make available the contact details of vessel owner, flag state and competent authorities in the seafarer’s country of residence. 10. The Seafarer making the complaint will have his/her rights protected and not prejudiced by the making of complaints.

### 三路诊断

| route | first_gold_rank | gold_ranks | top20_candidate_miss |
|---|---|---|---|
| bm25 | — | [] | True |
| vector | 4 | [4, 5] | False |
| hybrid | 9 | [9, 11] | False |

### bm25 top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | CMM:p16:2 | CMM p.16 §5 | 17.716617184498073 | 0.6392056096372032 | 0.6392056096372032 | Seafarer information & personal records safekeeping is all centralized in CMS. This includes paperwork for recruitment & promotion, training & certification, movements, employment contracts & benefits, payroll processing, performance apprai… |
| 2 |  | EMM:p101:1 | EMM p.101 §11 | 17.25665808666773 | 0.6331171646867676 | 0.6331171646867676 |  The Company will not tolerate any harassment or victimization of a colleague who raised a legitimate concern, or a concern that a colleague believed was legitimate.  Harassment or victimisation is a serious disciplinary of… |
| 3 |  | CMM:p51:0 | CMM p.51 §10 | 16.595461795163594 | 0.6239960006327655 | 0.6239960006327655 | b) Pre-joining briefing for female seafarer: i. Briefing to be conducted by crewing department and a senior female officer (ideally in person but otherwise by video call). ii. Explain importance of communicating directly an… |
| 4 |  | CMM:p51:2 | CMM p.51 §10 | 15.064180691791822 | 0.6010242615560594 | 0.6010242615560594 | • The general gist of how PCL handles such reports, the difficulties of conducting a fair investigation for both sides, and it is usually not easy to arrange crew change for both parties at short notice.… |
| 5 |  | CMM:p42:2 | CMM p.42 §10 | 15.004545292004844 | 0.6000727114522862 | 0.6000727114522862 | • 7 Beef dishes • 7 mutton/lamb dishes • 7 pork dishes • 7 seafood dishes g) Company appointed caters, if any, will be able to assist the Welfare & Mess Comm… |

### vector top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | CMM:p74:0 | CMM p.74 §12 | 0.68224097901455 | 0.841120489507275 | 0.841120489507275 | The procedure: The company provides several means for reporting & recording feedback, grievances and complaints through several platforms including the onboard complaints procedure, availability of DPA, the Open Reporting System… |
| 2 |  | CMM:p74:3 | CMM p.74 §12 | 0.6749402810039661 | 0.8374701405019831 | 0.8374701405019831 | Note: Seafarers are urged to resolve any complaint at lowest level or at Company level. However, in all cases crew may bypass the flow shown above and approach the Master, DPA or authority ashore directly. Seafarers… |
| 3 |  | CMM:p72:2 | CMM p.72 §12 | 0.6645193661301603 | 0.8322596830650801 | 0.8322596830650801 | 12.8. Complaint Procedure The company provides several means for reporting & recording feedback, grievances and complaints through several platforms including the onboard complaints procedure, availability of DPA, the Open Repor… |
| 4 | ✓ | CMM:p74:1 | CMM p.74 §12 | 0.6613574305092609 | 0.8306787152546304 | 0.8306787152546304 | 1. All complaints should be addressed to the Head of the Department of the Seafarer lodging the complaint or to the Seafarer’s superior officer. 2. The Head of Department or superior officer should then attempt to resol… |
| 5 | ✓ | CMM:p74:2 | CMM p.74 §12 | 0.6570218587061123 | 0.8285109293530561 | 0.8285109293530561 | 7. Once the complaint is received ashore, it will need to be resolved within 8 days, and appropriate to the seriousness of the issues involved. Where appropriate consultation to be held with the Seafarer concerned or… |

### hybrid top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | bm25 rank | vector rank | excerpt |
|---|---|---|---|---|---|---|---|---|---|
| 1 |  | CMM:p74:0 | CMM p.74 §12 | 127/4026 | 0.9621212121212122 | 0.841120489507275 | 6 | 1 | The procedure: The company provides several means for reporting & recording feedback, grievances and complaints through several platforms including the onboard complaints procedure, availability of DPA, the Open Reporting System… |
| 2 |  | EMM:p101:1 | EMM p.101 §11 | 32/1023 | 0.9540566959921799 | 0.8145447681887366 | 2 | 6 |  The Company will not tolerate any harassment or victimization of a colleague who raised a legitimate concern, or a concern that a colleague believed was legitimate.  Harassment or victimisation is a serious disciplinary of… |
| 3 |  | CMM:p51:2 | CMM p.51 §10 | 131/4288 | 0.9317863805970149 | 0.810157242810131 | 4 | 7 | • The general gist of how PCL handles such reports, the difficulties of conducting a fair investigation for both sides, and it is usually not easy to arrange crew change for both parties at short notice.… |
| 4 |  | CMM:p72:2 | CMM p.72 §12 | 19/630 | 0.9198412698412698 | 0.8322596830650801 | 10 | 3 | 12.8. Complaint Procedure The company provides several means for reporting & recording feedback, grievances and complaints through several platforms including the onboard complaints procedure, availability of DPA, the Open Repor… |
| 5 |  | CMM:p15:1 | CMM p.15 §4 | 142/5037 | 0.8598372046853285 | 0.7903637014287657 | 9 | 13 | Discrimination – Any practice of treating one person or group of people less fairly or less well than other people, based on: ethnicity, color, sex, disability, age, religion, political opinion, nationality, sexual orientation, or social or… |

**human_failure_tag**：`PENDING_HUMAN`　**human_failure_note**：（在 CSV 填写）

---

## PR04（TIER1）

- expected / type / language：answer / procedure / en
- question：According to the Permit-to-Work numbering-convention table in SMM 2.3, which jobs require a Permit to Work?
- required_elements：["Pump Room Entry (tankers)", "LO/TO Isolation", "Enclosed Space Entry", "Hot Work", "Cold Work", "Electrical/High-Voltage System Work", "Working on Pressure System", "Working Aloft/Overside", "Diving/Underwater Operations", "Lifting Operations"]
- acceptable_elements：["(prose list also on page) Work on critical equipment / taking it out of use"]
- citations：[{"doc_id": "SMM", "section": "2.3", "pdf_page": 35, "printed_page": "1 of 2", "quote": "Jobs requiring Permits to Work ... Pump Room Entry (Tankers) ... Working Aloft / Working Overside ... Diving / Underwater Operations ... Lifting Operations"}]
- query tokens（BM25 analyzer）：`according to the permit to work numbering convention table in smm 2 3 which jobs require a permit to work`

### gold（GoldChunkMap）

**SMM:p35:1** — SMM p.35 §2.3；与 query 共享 token：`jobs to work`

> Jobs requiring Permits to Work** Pump Room Entry (Tankers) LO/TO Isolation Enclosed Space Entry Hot Work Cold Work Electrical / High Voltage System Work Working on Pressure System Working Aloft / Working Overside Diving / Underwater Operations Lifting Operations **All PTWs are sequentially numbered within ABS Nautical Systems. Prior to commencement of work:

### 三路诊断

| route | first_gold_rank | gold_ranks | top20_candidate_miss |
|---|---|---|---|
| bm25 | — | [] | True |
| vector | 2 | [2] | False |
| hybrid | 10 | [10] | False |

### bm25 top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | SMM:p35:0 | SMM p.35 §2.3 | 32.72397751502192 | 0.7659393955891873 | 0.7659393955891873 | Applicable Form: Permit to Work Checklist. A Permit to Work (PTW) is a document that when fully filled out and signed by the authority named in it, allows commencement of the job mentioned. Its purpose is to ensure that conditions are safe… |
| 2 |  | SMM:p85:2 | SMM p.85 §2.19 | 29.93444427672733 | 0.7495896041346012 | 0.7495896041346012 | unshielded radioactive sources. General routine inspections (visual or wipe tests) shall not require a Cold Work Permit. ▪ Toxic Substance Exposure - Opening of pipelines and cargo equipment which may expose personnel to trapped toxic… |
| 3 |  | SMM:p66:0 | SMM p.66 §2.14 | 24.90300754997519 | 0.7134917389086974 | 0.7134917389086974 | • Non-Routine job • Involve Electrical work on equipment or near bare conductors. • Involve specialist isolation like High voltage or combustion. 2.14.3 Exemptions • At present the Electrical jobs like, all the jobs below and up t… |
| 4 |  | SMM:p68:0 | SMM p.68 §2.15 | 24.863776024530093 | 0.7131693367647836 | 0.7131693367647836 | • Concurrence from office should be sought in good time before the job is expected to commence. • The approval will be given by DPA or his alternate, by email, or fax after consultation with the Technical Department. Scope of the wo… |
| 5 |  | SMM:p31:0 | SMM p.31 §2.1 | 24.697639969088282 | 0.7117959605059916 | 0.7117959605059916 | 2.1.10 Risk Assessment Schematic Job Activity scheduled OR Task identified. Activity involves obvious risk? No Commence activity after toolbox talk and permit. Yes « Review and revise RA according to the prevailing circumstances. Fact… |

### vector top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | SMM:p35:0 | SMM p.35 §2.3 | 0.6391949686136075 | 0.8195974843068037 | 0.8195974843068037 | Applicable Form: Permit to Work Checklist. A Permit to Work (PTW) is a document that when fully filled out and signed by the authority named in it, allows commencement of the job mentioned. Its purpose is to ensure that conditions are safe… |
| 2 | ✓ | SMM:p35:1 | SMM p.35 §2.3 | 0.6039096178677769 | 0.8019548089338884 | 0.8019548089338884 | Jobs requiring Permits to Work** Pump Room Entry (Tankers) LO/TO Isolation Enclosed… |
| 3 |  | SMM:p81:0 | SMM p.81 §2.18 | 0.5801021509208136 | 0.7900510754604069 | 0.7900510754604069 | Applicable Forms: S-19 (Working Aloft or Overside Checklist); Permit to Work Checklist. Refer to: COSWP - Chapter 17 - Work at Height. Checklist S-19 and Permit to Work Checklists shall be used when working aloft, at heights or overside.… |
| 4 |  | SMM:p85:2 | SMM p.85 §2.19 | 0.5601596633321327 | 0.7800798316660664 | 0.7800798316660664 | unshielded radioactive sources. General routine inspections (visual or wipe tests) shall not require a Cold Work Permit. ▪ Toxic Substance Exposure - Opening of pipelines and cargo equipment which may expose personnel to trapped toxic… |
| 5 |  | SMM:p84:0 | SMM p.84 §2.19 | 0.5561145253723245 | 0.7780572626861623 | 0.7780572626861623 | Applicable Forms: S-9 (Lockout-Tagout Isolation Form); S-14 (Enclosed Space Entry Checklist); S-19 (Working Aloft or Overside Checklist); Permit to Work Checklist; S-12 (Work on Pipelines and Pressure Vessels Checklist) S-15 (Electrical Wo… |

### hybrid top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | bm25 rank | vector rank | excerpt |
|---|---|---|---|---|---|---|---|---|---|
| 1 |  | SMM:p35:0 | SMM p.35 §2.3 | 2/61 | 1.0 | 0.8195974843068037 | 1 | 1 | Applicable Form: Permit to Work Checklist. A Permit to Work (PTW) is a document that when fully filled out and signed by the authority named in it, allows commencement of the job mentioned. Its purpose is to ensure that conditions are safe… |
| 2 |  | SMM:p85:2 | SMM p.85 §2.19 | 63/1984 | 0.9684979838709677 | 0.7800798316660664 | 2 | 4 | unshielded radioactive sources. General routine inspections (visual or wipe tests) shall not require a Cold Work Permit. ▪ Toxic Substance Exposure - Opening of pipelines and cargo equipment which may expose personnel to trapped toxic… |
| 3 |  | SMM:p84:0 | SMM p.84 §2.19 | 131/4290 | 0.9313519813519814 | 0.7780572626861623 | 6 | 5 | Applicable Forms: S-9 (Lockout-Tagout Isolation Form); S-14 (Enclosed Space Entry Checklist); S-19 (Working Aloft or Overside Checklist); Permit to Work Checklist; S-12 (Work on Pipelines and Pressure Vessels Checklist) S-15 (Electrical Wo… |
| 4 |  | SMM:p66:0 | SMM p.66 §2.14 | 134/4473 | 0.9137044489157166 | 0.7614471695277287 | 3 | 11 | • Non-Routine job • Involve Electrical work on equipment or near bare conductors. • Involve specialist isolation like High voltage or combustion. 2.14.3 Exemptions • At present the Electrical jobs like, all the jobs below and up t… |
| 5 |  | SMM:p36:0 | SMM p.36 §2.3 | 2/67 | 0.9104477611940298 | 0.7725101129872625 | 7 | 7 | Permit to work shall become terminated if any of the following conditions occur:  The job is interrupted for more than 1 hour (e.g., meal break, bad weather).  Any of the conditions of the permit cease to be met (for example if t… |

**human_failure_tag**：`PENDING_HUMAN`　**human_failure_note**：（在 CSV 填写）

---

## CD01（TIER1）

- expected / type / language：answer / cross_doc / en
- question：For enclosed-space work, what is the maximum validity period of the entry permit and which checklist governs it, and if a person collapses inside, what is the first action to take and the key rule for the rescue team?
- required_elements：["entry permit validity not exceeding 8 hours (SMM)", "Checklist S-14 (SMM)", "first action: raise the alarm (ERM)", "do not attempt rescue alone; rescue team proceeds with breathing apparatus (ERM)"]
- acceptable_elements：["EEBD is for escape only, not to be used for rescue (SMM p74)"]
- citations：[{"doc_id": "SMM", "section": "2.16", "pdf_page": 73, "printed_page": "2 of 7", "quote": "Period of validity shall not exceed 8 hours ... S-14 (Enclosed Space Entry Checklist)"}, {"doc_id": "ERM", "section": "B.19", "pdf_page": 105, "printed_page": "1 of 1", "quote": "the first action must be to raise the alarm ... Do not try or attempt the rescue alone ... Rescue team to immediately proceed to entrance of enclosed space with additional rescue ... breathing apparatus"}, {"doc_id": "SMM", "section": "2.16", "pdf_page": 74, "printed_page": "3 of 7", "quote": "EEBD - for escape only; not to be used for rescue"}]
- query tokens（BM25 analyzer）：`for enclosed space work what is the maximum validity period of the entry permit and which checklist governs it and if a person collapses inside what is the first action to take and the key rule for the rescue team`

### gold（GoldChunkMap）

**ERM:p105:0** — ERM p.105 §B.19；与 query 共享 token：`a action and enclosed entry first for is of rescue space the to`

> Entry into an enclosed space i.e., cargo tank, cofferdam, double bottom, or similar enclosed spaces shall not be permitted without the permission from a responsible officer who is satisfied that the atmosphere within is safe in all respects for entry. When an accident involving injury to personnel occurs in an enclosed space, the first action must be to raise the alarm. Although speed is often vital in the interests of saving life, rescue operations should not be attempted until the necessary assistance and equipment have been mustered. There are many examples of lives being lost through hasty, ill-prepared rescue attempts. In the event of an emergency where rescue from a confined space is required the following points shall also be taken into account: IMMEDIATE ACTIONS:

**ERM:p105:1** — ERM p.105 §B.19；与 query 共享 token：`and enclosed entry for if is of rescue space team the to`

> • Sound the General Emergency Alarm and announce enclosed space rescue over PA. • Do not try or attempt the rescue alone. Wait for additional assistance. • Rescue team to immediately proceed to entrance of enclosed space with additional rescue equipment, breathing apparatus, EEBDs (for the casualty), lifelines and resuscitation equipment. • Ensure that the rescue party entering the enclosed space maintain close contact by intrinsically safe radios or pre-arranged code of signals with the coordinator outside. • Check the atmosphere of the enclosed space - 20.9% oxygen and no other gas. • Rescue team to proceed with breathing apparatus - never use EEBD for entry. • Ascertain if casualty is still breathing. If not breathing, remove from the space immediately for resuscitation. • If breathing, assess injuries before removing from enclosed space. If atmosphere is not verified as safe, provide air supply using extra SCBA or EEBD. • Backup team to rig rescue hoists and stretchers, ensure that additional air cylinders are available, set up the resuscitator, tend the lifelines, arrange additional lighting and ventilation as appropriate. • Refer to Section B.20 for Serious Injury and evacuation response procedures as required.

**SMM:p73:0** — SMM p.73 §2.16；与 query 共享 token：`a and checklist enclosed entry if permit space the work`

> 2.16.1 Enclosed Space Entry Permit Applicable Forms: S-9 (Lockout-Tagout Isolation) S-12 (Work on pipelines and pressure vessels) S-14 (Enclosed Space Entry Checklist). Once all preparations have been made, Checklist S-14 and all other applicable permits / checklists shall be filled in, signed by all relevant persons and completed, if possible, at the site and a copy displayed at the entrance.

**SMM:p73:1** — SMM p.73 §2.16；与 query 共享 token：`a and checklist enclosed entry for if is of period permit person space team the to validity which`

> • Name of the person carrying out gas checks and timings of the gas checks to be mentioned. • Generally, all checks listed must indicate “Yes” before entry is permitted. Lighting shall be adequate. • A separate Checklist S-14 shall be completed for each enclosed space to be entered. • Period of validity shall not exceed 8 hours. • Original copy of the checklist shall be furnished to the OOW for monitoring purposes, i.e. time of entry and exit. • OOW to stop the entry and inform the Master in case of discrepancies i.e. duration of entry exceeds the valid time frame. • Persons signing shall satisfy themselves that all points have been properly fulfilled. • Any change in conditions under which the permit was issued will render the permit invalid and persons shall exit at once. A new permit is to be issued prior to re-entry. • The Responsible Officer is usually the Chief Officer for entries on deck and the Chief Engineer for entries in the E/R. Where the CO or the CE is to enter the space, then the Responsible Officer will be the Master or 2/E. • Person supervising the entry shall not enter the enclosed space. A Team Leader for the entry is to be appointed. • If Senior Officers are entering, then only one Senior Officer from each department shall enter at a time.

**SMM:p74:0** — SMM p.74 §2.16；与 query 共享 token：`a and enclosed entry for if maximum of permit rescue space the to`

> • EEBD - for escape only; not to be used for rescue. 2.16.3 Marking of Enclosed Spaces All enclosed spaces shall have a marking, by means of stencilling in RED colour, at the man entry points indicating the atmospheric hazards that may be present. The stencils shall read as: ‘Enclosed & O2-Deficient Space’ If an enclosed space has been rendered safe for man entry, then a copy of the approved entry permit shall be placed at the entrance indicating this, until the permit time has lapsed. Any space that does not have such a sign shall not be entered. 2.16.4 Entry Preparation and Restriction on the Number of Spaces Entered Simultaneously Applicable Form: Q-14 (Risk Assessment Form). A risk assessment shall be made with Form Q-14, and all mitigating actions fulfilled. Entry into enclosed spaces shall be restricted to one space at any given time except for situations in shipyards or dry docks. However, when deemed necessary and provided that adequate resources are available, maximum of two spaces can be entered so far as the procedures are fully controlled in compliance with COSWP and the guidelines provided in this Section. When opening any entrances to a potentially dangerous space, precautions shall be taken in case of pressurized or unpressurized vapour / gases being released from the space.

### 三路诊断

| route | first_gold_rank | gold_ranks | top20_candidate_miss |
|---|---|---|---|
| bm25 | 1 | [1, 8, 10, 11, 12] | False |
| vector | 1 | [1, 3, 5, 8, 10] | False |
| hybrid | 1 | [1, 4, 6, 7, 8] | False |

### bm25 top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 | ✓ | SMM:p73:1 | SMM p.73 §2.16 | 44.89285286204485 | 0.8178269213820656 | 0.8178269213820656 | • Name of the person carrying out gas checks and timings of the gas checks to be mentioned. • Generally, all checks listed must indicate “Yes” before entry is permitted. Lighting shall be adequate. • A separate Checklist S-14 shall… |
| 2 |  | SMM:p85:2 | SMM p.85 §2.19 | 42.960673887182644 | 0.8111806503576201 | 0.8111806503576201 | unshielded radioactive sources. General routine inspections (visual or wipe tests) shall not require a Cold Work Permit. ▪ Toxic Substance Exposure - Opening of pipelines and cargo equipment which may expose personnel to trapped toxic… |
| 3 |  | SMM:p84:0 | SMM p.84 §2.19 | 41.50153283598976 | 0.8058310219261686 | 0.8058310219261686 | Applicable Forms: S-9 (Lockout-Tagout Isolation Form); S-14 (Enclosed Space Entry Checklist); S-19 (Working Aloft or Overside Checklist); Permit to Work Checklist; S-12 (Work on Pipelines and Pressure Vessels Checklist) S-15 (Electrical Wo… |
| 4 |  | SMM:p73:3 | SMM p.73 §2.16 | 36.77081748424094 | 0.7861914642956707 | 0.7861914642956707 | 2.16.2 Equipment to be Readied Equipment to be readied prior entry shall be at least: On standby outside the enclosed space: • Two self-contained breathing apparatus. • A stretcher. • First aid kit (to be checked and readily av… |
| 5 |  | SMM:p36:0 | SMM p.36 §2.3 | 36.44498185790368 | 0.7846914865723374 | 0.7846914865723374 | Permit to work shall become terminated if any of the following conditions occur:  The job is interrupted for more than 1 hour (e.g., meal break, bad weather).  Any of the conditions of the permit cease to be met (for example if t… |

### vector top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 | ✓ | SMM:p73:1 | SMM p.73 §2.16 | 0.6729053731839207 | 0.8364526865919604 | 0.8364526865919604 | • Name of the person carrying out gas checks and timings of the gas checks to be mentioned. • Generally, all checks listed must indicate “Yes” before entry is permitted. Lighting shall be adequate. • A separate Checklist S-14 shall… |
| 2 |  | SMM:p84:0 | SMM p.84 §2.19 | 0.65380614259758 | 0.8269030712987899 | 0.8269030712987899 | Applicable Forms: S-9 (Lockout-Tagout Isolation Form); S-14 (Enclosed Space Entry Checklist); S-19 (Working Aloft or Overside Checklist); Permit to Work Checklist; S-12 (Work on Pipelines and Pressure Vessels Checklist) S-15 (Electrical Wo… |
| 3 | ✓ | ERM:p105:0 | ERM p.105 §B.19 | 0.6498219730667534 | 0.8249109865333767 | 0.8249109865333767 | Entry into an enclosed space i.e., cargo tank, cofferdam, double bottom, or similar enclosed spaces shall not be permitted without the permission from a responsible officer who is satisfied that the atmosphere within is safe in all respects… |
| 4 |  | SMM:p85:2 | SMM p.85 §2.19 | 0.6388561952875641 | 0.819428097643782 | 0.819428097643782 | unshielded radioactive sources. General routine inspections (visual or wipe tests) shall not require a Cold Work Permit. ▪ Toxic Substance Exposure - Opening of pipelines and cargo equipment which may expose personnel to trapped toxic… |
| 5 | ✓ | SMM:p73:0 | SMM p.73 §2.16 | 0.6378087454081792 | 0.8189043727040897 | 0.8189043727040897 | 2.16.1 Enclosed Space Entry Permit Applicable Forms: S-9 (Lockout-Tagout Isolation) S-12 (Work on pipelines and pressure vessels) S-14 (Enclosed Space Entry Checklist). Once all preparations have been made, Checklist S-14 and all other a… |

### hybrid top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | bm25 rank | vector rank | excerpt |
|---|---|---|---|---|---|---|---|---|---|
| 1 | ✓ | SMM:p73:1 | SMM p.73 §2.16 | 2/61 | 1.0 | 0.8364526865919604 | 1 | 1 | • Name of the person carrying out gas checks and timings of the gas checks to be mentioned. • Generally, all checks listed must indicate “Yes” before entry is permitted. Lighting shall be adequate. • A separate Checklist S-14 shall… |
| 2 |  | SMM:p84:0 | SMM p.84 §2.19 | 125/3906 | 0.9760624679979518 | 0.8269030712987899 | 3 | 2 | Applicable Forms: S-9 (Lockout-Tagout Isolation Form); S-14 (Enclosed Space Entry Checklist); S-19 (Working Aloft or Overside Checklist); Permit to Work Checklist; S-12 (Work on Pipelines and Pressure Vessels Checklist) S-15 (Electrical Wo… |
| 3 |  | SMM:p85:2 | SMM p.85 §2.19 | 63/1984 | 0.9684979838709677 | 0.819428097643782 | 2 | 4 | unshielded radioactive sources. General routine inspections (visual or wipe tests) shall not require a Cold Work Permit. ▪ Toxic Substance Exposure - Opening of pipelines and cargo equipment which may expose personnel to trapped toxic… |
| 4 | ✓ | ERM:p105:0 | ERM p.105 §B.19 | 131/4284 | 0.93265639589169 | 0.8249109865333767 | 8 | 3 | Entry into an enclosed space i.e., cargo tank, cofferdam, double bottom, or similar enclosed spaces shall not be permitted without the permission from a responsible officer who is satisfied that the atmosphere within is safe in all respects… |
| 5 |  | SMM:p36:0 | SMM p.36 §2.3 | 134/4485 | 0.9112597547380156 | 0.8016367376919418 | 5 | 9 | Permit to work shall become terminated if any of the following conditions occur:  The job is interrupted for more than 1 hour (e.g., meal break, bad weather).  Any of the conditions of the permit cease to be met (for example if t… |

**human_failure_tag**：`PENDING_HUMAN`　**human_failure_note**：（在 CSV 填写）

---

## CD03（TIER2）

- expected / type / language：answer / cross_doc / en
- question：A maintenance task on critical equipment will take more than 8 hours. What approvals does it require, and who is the approving authority for the associated Permit to Work?
- required_elements：["RA + MOC + Office Approval", ">8h / as far as possible, ≥24 hours in advance", "Master is the PTW approving authority"]
- acceptable_elements：[]
- citations：[{"doc_id": "FMM", "section": "1.4.4", "pdf_page": 38, "printed_page": "3 of 4", "quote": "More than 8 Hours: Requires RA, MOC and Office Approval ... As far as possible task approval and RA shall be communicated to the Office at least 24 hours in advance"}, {"doc_id": "SMM", "section": "2.3", "pdf_page": 35, "printed_page": "1 of 2", "quote": "Master is the approving authority for all Permits to Work onboard"}]
- query tokens（BM25 analyzer）：`a maintenance task on critical equipment will take more than 8 hours what approvals does it require and who is the approving authority for the associated permit to work`

### gold（GoldChunkMap）

**FMM:p38:2** — FMM p.38 §1.4.4；与 query 共享 token：`8 a and equipment for hours is it maintenance more on task than the to work`

> b. Less than 8 Hours: Requires RA and Office Approval prior initiating the job. c. More than 8 Hours: Requires RA, MOC and Office Approval. As far as possible task approval and RA shall be communicated to the Office at least 24 hours in advance. 6. RA shall cover personnel, spares and tools, worst case scenarios, recovery and mitigation measures, commissioning and testing procedures, alternative back-up equipment / systems, necessary modification in operational procedures that may be required i.e., additional safety procedures etc. It shall also consider time of intended activity and duration of such work. The request shall clearly define the reasons for maintenance and the duration of unavailability of the equipment / system. 7. Office Approval shall be obtained prior to shut-down as per the circumstances of the case. The shut-down period shall be agreed upon between Vessel and the Office. 8. If the agreed shut-down period cannot be achieved and / or circumstances change, a further RA is to be conducted in co- ordination with the Office considering environmental conditions, crew fatigue, operational parameters etc. 9. On basis of the above RA and information provided, any extension or alternative actions shall be agreed upon and the

**SMM:p35:2** — SMM p.35 §2.3；与 query 共享 token：`and approving associated authority equipment for is on permit the to work`

>  For all above jobs, the Responsible Officer shall ensure that the permit is checked, filled, displayed and precautions / safety arrangements properly complied with.  The following are authorised as Responsible Officers onboard for PTWs and associated risk assessments: o Chief Officer or his alternate Officer on Duty (OOD) for Deck Department o Chief Engineer or his alternate Second Engineer  Master is the approving authority for all Permits to Work onboard. Permits to work are generally accompanied by:  Detailed RA - to be carried out during the planning stages keeping in mind the PEARS hazards and risks.  Proper Toolbox Meeting - to be conducted and all elements of RA and PTW checklist are discussed with work team.  Relevant Checklists - must be satisfactorily completed before the permit is signed.  Isolation / LOTO Certificate - In cases of work on equipment, machinery, or stored pressure apparatus.  Gas Measurement Certificate - In case of work in enclosed spaces (for tankers).  Written work procedure with additional instructions from office, ISGOTT or other industry inputs may be necessary.

### 三路诊断

| route | first_gold_rank | gold_ranks | top20_candidate_miss |
|---|---|---|---|
| bm25 | 8 | [8, 12] | False |
| vector | 2 | [2, 8] | False |
| hybrid | 4 | [4, 7] | False |

### bm25 top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | SMM:p29:0 | SMM p.29 §2.1 | 38.96771164942119 | 0.7957837999130146 | 0.7957837999130146 | Work on critical Tasks associated with disabling of critical equipment or disabled 7 Yes equipment /… |
| 2 |  | CMM:p46:1 | CMM p.46 §10 | 34.42347066797161 | 0.7748937701256694 | 0.7748937701256694 | Note: STCW 2010 Manila Amendments (Section A-VIII/1). If the flag state permits, then Companies may also note that the STCW amendments permit the following exceptions: • In case of over-riding operational conditions, t… |
| 3 |  | SMM:p85:2 | SMM p.85 §2.19 | 31.30715113645992 | 0.757911167319078 | 0.757911167319078 | unshielded radioactive sources. General routine inspections (visual or wipe tests) shall not require a Cold Work Permit. ▪ Toxic Substance Exposure - Opening of pipelines and cargo equipment which may expose personnel to trapped toxic… |
| 4 |  | QMM:p28:0 | QMM p.28 §1 | 29.922807721063485 | 0.7495166154177091 | 0.7495166154177091 | 1.8.14 Assessment of Occupational Health and Safety (OH&S) and Other Risks, Opportunities and Action Plan to Address Risks and Opportunities OH&S Risk OH&S Opportunities… |
| 5 |  | SMM:p36:0 | SMM p.36 §2.3 | 28.780157178804924 | 0.7421361663416505 | 0.7421361663416505 | Permit to work shall become terminated if any of the following conditions occur:  The job is interrupted for more than 1 hour (e.g., meal break, bad weather).  Any of the conditions of the permit cease to be met (for example if t… |

### vector top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | SMM:p29:0 | SMM p.29 §2.1 | 0.6619506440150712 | 0.8309753220075355 | 0.8309753220075355 | Work on critical Tasks associated with disabling of critical equipment or disabled 7 Yes equipment /… |
| 2 | ✓ | FMM:p38:2 | FMM p.38 §1.4.4 | 0.6410076814892037 | 0.8205038407446019 | 0.8205038407446019 | b. Less than 8 Hours: Requires RA and Office Approval prior initiating the job. c. More than 8 Hours: Requires RA, MOC and Office Approval. As far as possible task approval and RA shall be communicated to the Office at least 2… |
| 3 |  | SMM:p36:0 | SMM p.36 §2.3 | 0.6348260790020801 | 0.81741303950104 | 0.81741303950104 | Permit to work shall become terminated if any of the following conditions occur:  The job is interrupted for more than 1 hour (e.g., meal break, bad weather).  Any of the conditions of the permit cease to be met (for example if t… |
| 4 |  | SMM:p85:2 | SMM p.85 §2.19 | 0.6131400248064115 | 0.8065700124032058 | 0.8065700124032058 | unshielded radioactive sources. General routine inspections (visual or wipe tests) shall not require a Cold Work Permit. ▪ Toxic Substance Exposure - Opening of pipelines and cargo equipment which may expose personnel to trapped toxic… |
| 5 |  | FMM:p38:3 | FMM p.38 §1.4.4 | 0.6055959482725435 | 0.8027979741362717 | 0.8027979741362717 | Office will give its concurrence or ask for deferment of maintenance. RA shall be revisited and revised, as necessary, if any of the prevailing circumstances and conditions change or is expected to change (e.g., weather, personnel avail… |

### hybrid top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | bm25 rank | vector rank | excerpt |
|---|---|---|---|---|---|---|---|---|---|
| 1 |  | SMM:p29:0 | SMM p.29 §2.1 | 2/61 | 1.0 | 0.8309753220075355 | 1 | 1 | Work on critical Tasks associated with disabling of critical equipment or disabled 7 Yes equipment /… |
| 2 |  | SMM:p85:2 | SMM p.85 §2.19 | 127/4032 | 0.9606894841269841 | 0.8065700124032058 | 3 | 4 | unshielded radioactive sources. General routine inspections (visual or wipe tests) shall not require a Cold Work Permit. ▪ Toxic Substance Exposure - Opening of pipelines and cargo equipment which may expose personnel to trapped toxic… |
| 3 |  | SMM:p36:0 | SMM p.36 §2.3 | 128/4095 | 0.9533577533577534 | 0.81741303950104 | 5 | 3 | Permit to work shall become terminated if any of the following conditions occur:  The job is interrupted for more than 1 hour (e.g., meal break, bad weather).  Any of the conditions of the permit cease to be met (for example if t… |
| 4 | ✓ | FMM:p38:2 | FMM p.38 §1.4.4 | 65/2108 | 0.9404648956356736 | 0.8205038407446019 | 8 | 2 | b. Less than 8 Hours: Requires RA and Office Approval prior initiating the job. c. More than 8 Hours: Requires RA, MOC and Office Approval. As far as possible task approval and RA shall be communicated to the Office at least 2… |
| 5 |  | SMM:p35:0 | SMM p.35 §2.3 | 2/67 | 0.9104477611940298 | 0.7995037481587854 | 7 | 7 | Applicable Form: Permit to Work Checklist. A Permit to Work (PTW) is a document that when fully filled out and signed by the authority named in it, allows commencement of the job mentioned. Its purpose is to ensure that conditions are safe… |

**human_failure_tag**：`PENDING_HUMAN`　**human_failure_note**：（在 CSV 填写）

---

## ML01（TIER1）

- expected / type / language：answer / multilingual / zh
- question：晋升为船长前，大副必须与即将离任的船长并行航行至少多少天？
- required_elements：["5 天 / 5 days"]
- acceptable_elements：[]
- citations：[{"doc_id": "CMM", "section": "9", "pdf_page": 32, "printed_page": "32 of 133", "quote": "a minimum of 5 days with the off-signing Master"}]
- query tokens（BM25 analyzer）：`晋升为船长前 大副必须与即将离任的船长并行航行至少多少天`

### gold（GoldChunkMap）

**CMM:p32:2** — CMM p.32 §9；与 query 共享 token：`∅`

> Category I – Overlap Period II – Overlap Period (Ex company Staff and (New Staff or on not on promotion) promotion) Master 24 hours 48 hours* nd Chief Engineer, Chief Officer and 2 24 hours 48 hours Engineer Deck Officers and Engineers 12 hours 12 hours Other Ranks 8 Hours 8 Hours * When a Chief Officer is being promoted to the rank of Master, he should sail in parallel for a minimum of 5 days with the off-signing Master.

### 三路诊断

| route | first_gold_rank | gold_ranks | top20_candidate_miss |
|---|---|---|---|
| bm25 | — | [] | True |
| vector | 2 | [2] | False |
| hybrid | 2 | [2] | False |

### bm25 top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| — |  | （该路返回 0 条） |  |  |  |  |  |

### vector top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | CMM:p123:1 | CMM p.123 §Appendix VI | 0.6679956245101529 | 0.8339978122550764 | 0.8339978122550764 | For New Hire, ≥48 hours Go back to sail as Chief hand over period. For Officer for minimum one Pr… |
| 2 | ✓ | CMM:p32:2 | CMM p.32 §9 | 0.6355023157301078 | 0.8177511578650539 | 0.8177511578650539 | Category I – Overlap Period II – Overlap Period (Ex company Staff and (New Staff or on… |
| 3 |  | CMM:p124:1 | CMM p.124 §Appendix VI | 0.614701097059307 | 0.8073505485296535 | 0.8073505485296535 | For New Hire, hand over Period, ≥48 Go back to sail as hours hand over Second Engineer for… |
| 4 |  | CMM:p21:0 | CMM p.21 §7 | 0.5804592641788011 | 0.7902296320894006 | 0.7902296320894006 | Crewing Policies **Internal promote must meet the minimum experience criteria for the current rank. (eg. When promoting to C/O, the crew has to meet 2/O experience criteria of 6 months.) Note: a) All seafarers are to complete a Crew Evalu… |
| 5 |  | CMM:p54:2 | CMM p.54 §11 | 0.5703614001835052 | 0.7851807000917526 | 0.7851807000917526 | 11.8. Accounting Procedures Following are standard accounting procedures adopted: 11.8.1. To ensure correct payment, all crew movements will be done within three working days of them occurring, allowing for vessel opera… |

### hybrid top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | bm25 rank | vector rank | excerpt |
|---|---|---|---|---|---|---|---|---|---|
| 1 |  | CMM:p123:1 | CMM p.123 §Appendix VI | 1/61 | 0.5 | 0.8339978122550764 | — | 1 | For New Hire, ≥48 hours Go back to sail as Chief hand over period. For Officer for minimum one Pr… |
| 2 | ✓ | CMM:p32:2 | CMM p.32 §9 | 1/62 | 0.49193548387096775 | 0.8177511578650539 | — | 2 | Category I – Overlap Period II – Overlap Period (Ex company Staff and (New Staff or on… |
| 3 |  | CMM:p124:1 | CMM p.124 §Appendix VI | 1/63 | 0.48412698412698413 | 0.8073505485296535 | — | 3 | For New Hire, hand over Period, ≥48 Go back to sail as hours hand over Second Engineer for… |
| 4 |  | CMM:p21:0 | CMM p.21 §7 | 1/64 | 0.4765625 | 0.7902296320894006 | — | 4 | Crewing Policies **Internal promote must meet the minimum experience criteria for the current rank. (eg. When promoting to C/O, the crew has to meet 2/O experience criteria of 6 months.) Note: a) All seafarers are to complete a Crew Evalu… |
| 5 |  | CMM:p54:2 | CMM p.54 §11 | 1/65 | 0.46923076923076923 | 0.7851807000917526 | — | 5 | 11.8. Accounting Procedures Following are standard accounting procedures adopted: 11.8.1. To ensure correct payment, all crew movements will be done within three working days of them occurring, allowing for vessel opera… |

**human_failure_tag**：`PENDING_HUMAN`　**human_failure_note**：（在 CSV 填写）

---

## ML02（TIER1）

- expected / type / language：answer / multilingual / tl
- question：Gaano kadalas dapat isagawa ang drug test sa mga tripulante — sa mga tanker at sa mga non-tanker?
- required_elements：["tankers: every 6 months and at random", "dry vessels: Not Required"]
- acceptable_elements：[]
- citations：[{"doc_id": "QMM", "section": "2", "pdf_page": 33, "printed_page": "3 of 5", "quote": "At least once every 6 Months ... For Dry Vessels ... Not Required"}]
- query tokens（BM25 analyzer）：`gaano kadalas dapat isagawa ang drug test sa mga tripulante sa mga tanker at sa mga non tanker`

### gold（GoldChunkMap）

**QMM:p33:0** — QMM p.33 §2；与 query 共享 token：`at drug test`

> Drug & Alcohol (D&A) Testing Requirements For Tankers For Dry Vessels • At least once every Month. • At least once every Month. (1 )+ • Initiated onboard by the Master randomly. • Initiated onboard by the Master randomly. Monthly Onboard • Administered using shipboard test kit. • Administered using shipboard test kit. Alcohol Testing • Results for all crew are to be recorded in • Results for all crew are to be recorded in Form C-21. Form C-21.

**QMM:p33:2** — QMM p.33 §2；与 query 共享 token：`at drug test`

> • Conducted without any pre-emptive warning or notification, through an approved sample collector or medical laboratory designated (3) ^Unannounced by the Company. Drug & Alcohol • At least once every 6 Months and at • Not Required. Testing By random. Company • Copies of these test results will be sent to (External) the Master for vessel’s records, and should be kept strictly confidential. • Initiated by the Company. Drug & Alcohol The Company reserves the right to ask an employee to be tested for drugs and/or alcohol, Test during when the Company, its agents or Ship’s Officers have reasonable cause to believe that a Employment particular person has used illegal drugs and/or has excessive alcohol levels in his Tenure physiological system.

### 三路诊断

| route | first_gold_rank | gold_ranks | top20_candidate_miss |
|---|---|---|---|
| bm25 | — | [] | True |
| vector | 1 | [1, 2] | False |
| hybrid | 4 | [4, 6] | False |

### bm25 top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | ERM:p40:1 | ERM p.40 §6 | 23.77102375802702 | 0.703888159516541 | 0.703888159516541 | 3) Arrange SA Surveyor (only for cases X X X X X X X exceeding… |
| 2 |  | ERM:p130:2 | ERM p.130 §D.1 | 23.77102375802702 | 0.703888159516541 | 0.703888159516541 | 3) Arrange SA Surveyor (only for cases X X X X X X X exceedin… |
| 3 |  | ERM:p39:2 | ERM p.39 §6 | 22.90889828483951 | 0.6961308180709651 | 0.6961308180709651 | ad) Salvage Association (SA) Surveyor X X X X X X X Report, if a… |
| 4 |  | CMM:p108:0 | CMM p.108 §Appendix III | 22.553947703095925 | 0.6928175933928594 | 0.6928175933928594 | Addresses for Complaint Submittal Bangladesh Commodore Md Nizamul Haque, (TAS) Director General Department of Shipping BIWTA Bhaban (8th floor) 141-143 Motijheel C/A Dhaka 1000, Bangladesh Phone: +880 2 9513305 Fax: +880 2 9587301 Email: i… |
| 5 |  | ERM:p129:2 | ERM p.129 §D.1 | 22.28040421048467 | 0.6902145358901051 | 0.6902145358901051 | ab) Deviation Certificate, if applicable. X X X X X X X X X X… |

### vector top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 | ✓ | QMM:p33:2 | QMM p.33 §2 | 0.6861058581862864 | 0.8430529290931432 | 0.8430529290931432 | • Conducted without any pre-emptive warning or notification, through an approved sample collector or medical laboratory designated (3) ^Unannounced by the… |
| 2 | ✓ | QMM:p33:0 | QMM p.33 §2 | 0.6793230798607703 | 0.8396615399303852 | 0.8396615399303852 | Drug & Alcohol (D&A) Testing Requirements For Tankers For Dry Vessels • At least once every Month. • At least… |
| 3 |  | QMM:p33:1 | QMM p.33 §2 | 0.6303115163350417 | 0.8151557581675208 | 0.8151557581675208 | • At least once every 2 Months. • At least once every 2 Months. + (2 ) • Initiated by the Company or Master. • Initiated by the Company or Master. *Unannounced •… |
| 4 |  | QMM:p33:3 | QMM p.33 §2 | 0.6009086138280716 | 0.8004543069140357 | 0.8004543069140357 | Breaches of The Company / Office is to be informed immediately of the details of any personnel who are Company’s Drug found in violation of the Company’s Drug & Alcohol Po… |
| 5 |  | QMM:p129:1 | QMM p.129 §A.1 | 0.597749491995055 | 0.7988747459975275 | 0.7988747459975275 |  Ensuring compliance with this policy which may include but is not limited to drug and alcohol testing of seagoing and/or shore-based staff during pre-employment, periodical medical assessments, post-incident testing, fo… |

### hybrid top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | bm25 rank | vector rank | excerpt |
|---|---|---|---|---|---|---|---|---|---|
| 1 |  | QMM:p32:3 | QMM p.32 §2 | 69/2380 | 0.8842436974789916 | 0.7981725751663752 | 10 | 8 | 2.3 Implementation of the Drug and Alcohol Policy The Crewing Department or Manning Agents ashore shall at the time of recruitment, and the Master and Senior Officers shall at the time of boarding, have the responsibility for ensuring that… |
| 2 |  | QMM:p32:5 | QMM p.32 §2 | 140/4899 | 0.8716064502959787 | 0.793238359310375 | 9 | 11 | (Applicable to non-Tankers) It is recognized that although consumption of alcohol is prohibited on board (non-tanker), seafarer may on occasion consume alcohol during shore liberty. A seafarer on ships article must comply with Company rules… |
| 3 |  | ERM:p40:1 | ERM p.40 §6 | 1/61 | 0.5 | 0.703888159516541 | 1 | — | 3) Arrange SA Surveyor (only for cases X X X X X X X exceeding… |
| 4 | ✓ | QMM:p33:2 | QMM p.33 §2 | 1/61 | 0.5 | 0.8430529290931432 | — | 1 | • Conducted without any pre-emptive warning or notification, through an approved sample collector or medical laboratory designated (3) ^Unannounced by the… |
| 5 |  | ERM:p130:2 | ERM p.130 §D.1 | 1/62 | 0.49193548387096775 | 0.703888159516541 | 2 | — | 3) Arrange SA Surveyor (only for cases X X X X X X X exceedin… |

**human_failure_tag**：`PENDING_HUMAN`　**human_failure_note**：（在 CSV 填写）

---

## ML03（TIER1）

- expected / type / language：answer / multilingual / hi
- question：आपातकाल के बारे में जानने के बाद मास्टर को DPA को कितने समय के भीतर सूचित करना चाहिए?
- required_elements：["30 minutes / 30 मिनट"]
- acceptable_elements：[]
- citations：[{"doc_id": "ERM", "section": "4.1", "pdf_page": 14, "printed_page": "2 of 9", "quote": "no later than 30 minutes of first becoming aware"}]
- query tokens（BM25 analyzer）：`आपातकाल के बारे में जानने के बाद मास्टर को dpa को कितने समय के भीतर सूचित करना चाहिए`

### gold（GoldChunkMap）

**ERM:p14:0** — ERM p.14 §4.1；与 query 共享 token：`dpa`

> 4.1.2 Line of Communication The DPA is responsible for the overall management of the Emergency response and act as the main contact person ashore for the Emergency response. In the event the DPA is not available, the ADPA shall act in the capacity as the DPA. In an event of an Emergency involving a Group owned ship, the Master is fully in-charge of all shipboard operations. The Master’s priority is the safety of personnel and Group owned vessel and to take all necessary actions to prevent the escalation of the Emergency. An immediate initial verbal notification to the DPA must be initiated by the Master at the earliest opportunity (no later than 30 minutes of first becoming aware of the situation) in order to enable the DPA to assist the vessel in handling the Emergency. The DPA must be notified at first instance for all Emergencies. Thereafter, the DPA shall inform, depending on type and level of emergency, by telephone: a. GM; b. Head of Operation; c. Insurance Department; d. Head of Human Resources, if the Emergency is particular to the safety of shore based employees; e. Head of Crewing (if the Emergency is particular to safety of Seafarer); f. Head of Technical (if the Emergency is particular to hull, machinery etc); g. Marine Manager.

### 三路诊断

| route | first_gold_rank | gold_ranks | top20_candidate_miss |
|---|---|---|---|
| bm25 | 4 | [4] | False |
| vector | 2 | [2] | False |
| hybrid | 1 | [1] | False |

### bm25 top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | QMM:p47:0 | QMM p.47 §4 | 6.284953661909055 | 0.3859362324505553 | 0.3859362324505553 | If any staff onboard find that avenues of communication to superiors are closed to their concerns on safety, health, and environmental matters, they have a right to contact and communicate such matters directly to the DPA through the contac… |
| 2 |  | QMM:p69:0 | QMM p.69 §11 | 6.252805943209457 | 0.3847216268414209 | 0.3847216268414209 | 11.1.4 Company Circulars and Alerts Company Circular Prepared by: Reviewed and Approved by: ▪ Health and Safety ▪ Navigation ▪ Marine ▪ Alerts… |
| 3 |  | QMM:p45:3 | QMM p.45 §3 | 5.984940925121835 | 0.37441120071428846 | 0.37441120071428846 | 3.4 Responsibilities of Personnel Onboard Refer to Crewing Management Manual (CMM) – Appendix 2 & 6 for Responsibilities of the Shipboard personnels. 3.5 Responsibility for Resources and Support to DPA Refer to: Quality Management Ma… |
| 4 | ✓ | ERM:p14:0 | ERM p.14 §4.1 | 5.719308047978424 | 0.3638396824161706 | 0.3638396824161706 | 4.1.2 Line of Communication The DPA is responsible for the overall management of the Emergency response and act as the main contact person ashore for the Emergency response. In the event the DPA is not available, the ADPA shall act in the… |
| 5 |  | ERM:p20:0 | ERM p.20 §4.1 | 5.662917481202267 | 0.36154934021701735 | 0.36154934021701735 | 4.1.8 Notification Method Incidents Other Incidents Incidents Deliverable Actual (Severity 1&2)/ Report By… |

### vector top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | excerpt |
|---|---|---|---|---|---|---|---|
| 1 |  | ERM:p21:0 | ERM p.21 §4.1 | 0.6386407470391211 | 0.8193203735195606 | 0.8193203735195606 | REPORTING & COMMUNICATION PROTOCOL DURING EMERGENCIES AND INCIDENTS In cases of all emergencies and / or incidents of actual Severity 4 / 5 or involving pollution, the protocol for reporting is as under: 1st Step: Call DPA within 30 mins o… |
| 2 | ✓ | ERM:p14:0 | ERM p.14 §4.1 | 0.6370484458613188 | 0.8185242229306594 | 0.8185242229306594 | 4.1.2 Line of Communication The DPA is responsible for the overall management of the Emergency response and act as the main contact person ashore for the Emergency response. In the event the DPA is not available, the ADPA shall act in the… |
| 3 |  | ERM:p20:0 | ERM p.20 §4.1 | 0.6275515733596708 | 0.8137757866798354 | 0.8137757866798354 | 4.1.8 Notification Method Incidents Other Incidents Incidents Deliverable Actual (Severity 1&2)/ Report By… |
| 4 |  | ERM:p20:4 | ERM p.20 §4.1 | 0.6087382957095687 | 0.8043691478547843 | 0.8043691478547843 | Master/CE Preliminary (Incident Severity DPA, Fleet Director, Other Dept. Report - below 3)… |
| 5 |  | ERM:p20:1 | ERM p.20 §4.1 | 0.5979391248176114 | 0.7989695624088057 | 0.7989695624088057 | Fleet Director, Group Crisis As per discretion of Within 2 hours NA DPA HSEQ and subsequently to Response… |

### hybrid top 5

| rank | gold | chunk_id | doc/page/section | raw | relevance | match | bm25 rank | vector rank | excerpt |
|---|---|---|---|---|---|---|---|---|---|
| 1 | ✓ | ERM:p14:0 | ERM p.14 §4.1 | 63/1984 | 0.9684979838709677 | 0.8185242229306594 | 4 | 2 | 4.1.2 Line of Communication The DPA is responsible for the overall management of the Emergency response and act as the main contact person ashore for the Emergency response. In the event the DPA is not available, the ADPA shall act in the… |
| 2 |  | ERM:p20:0 | ERM p.20 §4.1 | 128/4095 | 0.9533577533577534 | 0.8137757866798354 | 5 | 3 | 4.1.8 Notification Method Incidents Other Incidents Incidents Deliverable Actual (Severity 1&2)/ Report By… |
| 3 |  | ERM:p21:0 | ERM p.21 §4.1 | 134/4453 | 0.9178082191780822 | 0.8193203735195606 | 13 | 1 | REPORTING & COMMUNICATION PROTOCOL DURING EMERGENCIES AND INCIDENTS In cases of all emergencies and / or incidents of actual Severity 4 / 5 or involving pollution, the protocol for reporting is as under: 1st Step: Call DPA within 30 mins o… |
| 4 |  | QMM:p81:0 | QMM p.81 §12 | 34/1155 | 0.8978354978354979 | 0.7850069697217836 | 6 | 10 | For ships, it is important to extend a copy of the findings to the DPA as soon as is practicable after completion of the audit, followed by the proposed CAPAs. If there are no major findings (which must be dealt with immediately), DPA or h… |
| 5 |  | ERM:p20:4 | ERM p.20 §4.1 | 69/2368 | 0.8887246621621622 | 0.8043691478547843 | 14 | 4 | Master/CE Preliminary (Incident Severity DPA, Fleet Director, Other Dept. Report - below 3)… |

**human_failure_tag**：`PENDING_HUMAN`　**human_failure_note**：（在 CSV 填写）

---

## 附录 A · 全部 31 道可答题的 ranking diagnostic（机械值，不是 failure label）

| question_id | language | gold_count | bm25 first / gold_ranks | vector first / gold_ranks | hybrid first / gold_ranks |
|---|---|---|---|---|---|
| FL01 | en | 1 | 1 / [1] | 1 / [1] | 1 / [1] |
| FL02 | en | 1 | 1 / [1] | 1 / [1] | 1 / [1] |
| FL03 | en | 1 | 1 / [1] | 1 / [1] | 1 / [1] |
| FL04 | en | 1 | 3 / [3] | 2 / [2] | 3 / [3] |
| FL05 | en | 1 | 1 / [1] | 2 / [2] | 1 / [1] |
| FL06 | en | 4 | 1 / [1, 2, 5, 8] | 1 / [1, 2, 3, 4] | 1 / [1, 2, 4, 5] |
| FL07 | en | 3 | 1 / [1, 3, 4] | 1 / [1, 2, 4] | 1 / [1, 2, 4] |
| FL08 | en | 1 | 1 / [1] | 7 / [7] | 2 / [2] |
| FL09 | en | 1 | 1 / [1] | 1 / [1] | 1 / [1] |
| FL10 | en | 1 | 1 / [1] | 1 / [1] | 1 / [1] |
| FL11 | en | 1 | 1 / [1] | 1 / [1] | 1 / [1] |
| FL12 | en | 1 | 1 / [1] | 1 / [1] | 1 / [1] |
| FL13 | en | 1 | 3 / [3] | 2 / [2] | 2 / [2] |
| FL14 | en | 1 | 5 / [5] | — / [] | 13 / [13] |
| FL15 | en | 1 | 1 / [1] | 1 / [1] | 1 / [1] |
| CN01 | en | 1 | 2 / [2] | 1 / [1] | 1 / [1] |
| CN02 | en | 1 | 7 / [7] | 1 / [1] | 3 / [3] |
| CN03 | en | 2 | 2 / [2] | 1 / [1] | 1 / [1] |
| CN04 | en | 1 | 9 / [9] | 1 / [1] | 4 / [4] |
| PR01 | en | 2 | 19 / [19] | 4 / [4, 12] | 4 / [4] |
| PR02 | en | 1 | 2 / [2] | 1 / [1] | 1 / [1] |
| PR03 | en | 2 | — / [] | 4 / [4, 5] | 9 / [9, 11] |
| PR04 | en | 1 | — / [] | 2 / [2] | 10 / [10] |
| PR05 | en | 1 | 3 / [3] | 1 / [1] | 2 / [2] |
| PR06 | en | 2 | 5 / [5] | 1 / [1] | 1 / [1] |
| CD01 | en | 5 | 1 / [1, 8, 10, 11, 12] | 1 / [1, 3, 5, 8, 10] | 1 / [1, 4, 6, 7, 8] |
| CD02 | en | 2 | 1 / [1, 2] | 1 / [1, 4] | 1 / [1, 3] |
| CD03 | en | 2 | 8 / [8, 12] | 2 / [2, 8] | 4 / [4, 7] |
| ML01 | zh | 1 | — / [] | 2 / [2] | 2 / [2] |
| ML02 | tl | 2 | — / [] | 1 / [1, 2] | 4 / [4, 6] |
| ML03 | hi | 1 | 4 / [4] | 2 / [2] | 1 / [1] |

## 附录 B · TOP_K_RETRIEVE = 20 的 evidence（只准备证据，不做 L1 决策）

- bm25：top-20 无 gold 的可答题 4 / 31：['PR03', 'PR04', 'ML01', 'ML02']
- vector：top-20 无 gold 的可答题 1 / 31：['FL14']
- hybrid：top-20 无 gold 的可答题 0 / 31：[]

只是当前 39 题评测集上的 evidence，不自动证明 20 普遍足够。

## 附录 C · refuse / trap 题（不进入 candidate_retrieval_miss 分母；本轮不赋 refusal_miss）

| question_id | type | bm25 max_match / top1 | vector max_match / top1 | hybrid max_match / top1 |
|---|---|---|---|---|
| TR01 | trap | 0.5811750600981916 / QMM:p106:3 | 0.7792718520928508 / QMM:p106:3 | 0.7792718520928508 / QMM:p106:3 |
| TR02 | trap | 0.684450657336873 / SMM:p52:1 | 0.7675266230855678 / FMM:p218:1 | 0.7675266230855678 / FMM:p218:1 |
| TR03 | trap | 0.6976430971991606 / FMM:p175:2 | 0.7724093968514165 / EMM:p29:2 | 0.7724093968514165 / EMM:p29:2 |
| TR04 | trap | 0.6259404236727674 / CMM:p88:0 | 0.7780620925196177 / EMM:p83:0 | 0.7780620925196177 / CMM:p68:0 |
| TR05 | trap | 0.638836037691105 / NPM:p27:3 | 0.7577088026949319 / NPM:p79:0 | 0.7577088026949319 / NPM:p24:2 |
| TR06 | trap | 0.6341958624753293 / CMM:p15:2 | 0.7552945907939674 / CMM:p28:2 | 0.7552945907939674 / CMM:p41:0 |
| TR07 | trap | 0.5294641590434965 / QMM:p9:1 | 0.7487373263590936 / SMM:p11:2 | 0.7487373263590936 / QMM:p9:1 |
| TR08 | trap | 0.6235160629683949 / FMM:p81:0 | 0.7548146640308633 / FMM:p4:0 | 0.7548146640308633 / FMM:p4:0 |
