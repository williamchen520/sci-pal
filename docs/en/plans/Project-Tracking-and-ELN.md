# Work Plan: Project Tracking and Experiment Records (ELN)

> Status: Pending review  
> Scope: Item 2 (projects, designs, protocol.io, experiment records, runs, audit, electronic signatures, permissions)  
> Fit: A complete ELN; first reach "ELN with audit" without claiming regulatory certification.

## 1. Decisions and Assumptions

| Item | Decision |
|---|---|
| Goal | Complete ELN |
| Compliance | Follow institutional research integrity (B) first; do not claim 21 CFR Part 11 |
| Electronic signature | Required |
| protocol.io | Snapshot + manual refresh |
| Experiment / Run | Keep both levels |
| Protocol | Every experiment must reference a protocol version |
| Member cross-visibility | Not allowed |
| PI access | Must request; member approval |
| Raw data | Store paths only; DSH can call them |
| Legacy data | Migrate the existing protocol/run tables |

## 2. Compliance Boundaries

To be explicit:

```
This plan implements audit trail, versioning, electronic signatures, and permissions.
It does not include formal system validation (IQ/OQ/PQ) for 21 CFR Part 11 / GLP.
```

If regulatory compliance is pursued later:

- A separate validation plan;
- SOPs;
- Training;
- Retention policy;
- Vendor audits.

## 3. Object Model

```
Project
├─ Design
├─ Protocol (snapshot/version)
├─ Experiment
│  ├─ Run
│  ├─ Deviation
│  ├─ DataRef
│  └─ Signature
├─ NotebookEntry
├─ Literature
└─ Audit
```

## 4. Project

Fields:

- Title, abstract;
- PI;
- Members and roles;
- Status: planning / active / paused / completed / archived;
- Start/end dates;
- Milestones;
- Workspace;
- Data class;
- Linked literature;
- Linked digests.

Rules:

- A project belongs to one workspace;
- Cross-workspace projects are not supported;
- Read-only after archiving;
- PIs can see project metadata and members but not member experiment content (unless approved).

## 5. Design (Study Design)

Fields:

```yaml
research_question:
hypothesis:
objectives:
endpoints:
variables:
controls:
sample_size:
statistical_plan:
ethics_approval:
preregistration:
timeline:
protocols: []
```

- Versioned;
- Can link multiple protocols;
- Exportable;
- Changes require a new revision.

## 6. Protocol

### Sources

- protocols.io snapshots;
- Locally hand-written protocols;
- Other repositories can be added later.

### Snapshot

```text
protocol_id
source: protocols_io | local
external_id
doi
url
version
license
snapshot_path
fetched_at
```

- Pinned version;
- Manual refresh;
- Old versions retained;
- No automatic sync;
- License travels with the snapshot.

### Experiment Binding

An Experiment must specify:

```
protocol_id
protocol_version
```

A "formal experiment without a protocol" is not allowed.

Exploratory experiments must also use a local protocol (an empty template is acceptable).

## 7. Experiment / Run

### Experiment

- Title;
- Purpose;
- Protocol version;
- Design reference;
- Operator;
- Start/end;
- Status;
- Conclusion;
- Data class;
- Private by default.

### Run

- run_id;
- Actual parameters;
- Actual conditions;
- Observations;
- Results;
- Failures/anomalies;
- Attachment references;
- Operator;
- Timestamp.

### Planned vs. Actual

Structured comparison:

| Field | Protocol planned | Run actual | Deviation |
|---|---|---|---|
| Sample size | 20 | 18 | -2 |
| Dose | 10 mg | 8 mg | -20% |
| Duration | 4 weeks | 3 weeks | -1 week |

Deviation fields:

```
field
planned
actual
reason
impact
corrective_action
```

## 8. Revisions, Audit, Signatures

### Revision

- Append-only;
- Never overwrites history;
- Each revision has a hash;
- The current pointer points to the latest.

### Audit

Records:

- Who;
- When;
- Which field;
- Old/new value;
- Reason;
- Associated signature.

### E-signature

```text
signer
meaning: author | reviewer | approver
timestamp
record_hash
re_auth_method
```

Rules:

- Re-authenticate before signing;
- The signature is bound to the revision hash;
- Locked after signing;
- Changes require a new revision;
- Audit records the reason.

No claim of legal effect; this is for research record integrity only.

## 9. Permissions

### Defaults

- Experiment records are private;
- Members cannot see each other's records;
- PIs cannot view them directly;
- Administrators cannot see content;
- Project metadata is visible to members.

### PI Request Flow

```
PI request
→ member approve/deny
→ time-bound read-only
→ audit
→ expire/revoke
```

- PIs cannot override;
- Members may deny;
- Approval scope: a single experiment or a time window;
- Export is not allowed by default;
- Members can see the request log.

### Project Closeout

Access does not open automatically; the request flow still applies.

## 10. Raw Data DataRef

Stores references only:

```yaml
path:
host:
protocol: local | smb | nfs
checksum:
size:
data_class:
access_note:
```

Rules:

- Not copied into the ELN;
- DSH read-only access;
- Path allowlist;
- Reject `..`;
- Log access audits;
- Mark broken paths.

### Important Limitation

Application-level permissions cannot replace OS permissions.

If a PI is approved but lacks OS permissions, they still cannot read the file;  
if a PI has OS permissions, the ELN cannot prevent direct reads.

Therefore you need:

- OS ACLs;
- Shared groups;
- Or a data service proxy.

The plan document must state this boundary.

## 11. VFS Mapping

```text
/workspaces/<ws>/projects/<project>/
├─ project.json
├─ design/
├─ protocols/<protocol>/
├─ experiments/<exp>/
│  ├─ experiment.json
│  ├─ runs/<run>/
│  ├─ deviations/
│  └─ signatures/
├─ literature/
└─ exports/
```

- `data_class`;
- Old versions are read-only;
- Audit files cannot be deleted;
- Archives are read-only.

## 12. Templates

Domain packs provide:

```text
packs/<id>/eln/
├─ design.yaml
├─ experiment.yaml
├─ run.yaml
└─ deviations.yaml
```

Examples:

- Wet-lab experiments;
- Animal studies;
- Clinical trials;
- Dry-lab/computational;
- Materials/chemistry.

## 13. Relation to Literature and Digests

- Projects link literature;
- Experiments can cite literature;
- Digest items can be added to projects;
- Designs can cite evidence;
- Private experiments are never sent to the cloud automatically.

## 14. AI Assistance

Allowed:

- Summarize experiment records;
- Compare design vs. actual;
- Extract deviations;
- Generate protocol drafts;
- Link literature.

Limits:

- Private data uses local/HPC only;
- Generated content is marked draft;
- No automatic signing;
- No automatic changes to records.

## 15. Data Model

```sql
projects(
  project_id, workspace_id, owner_user_id,
  title, status, data_class, created_at
)

project_members(project_id, user_id, role)

project_designs(
  design_id, project_id, revision, content_json,
  created_by, created_at
)

protocols(
  protocol_id, project_id, source, external_id,
  doi, url, version, license, snapshot_path
)

experiments(
  experiment_id, project_id, protocol_id,
  protocol_version, owner_user_id, title,
  status, data_class, current_revision_id
)

experiment_revisions(
  revision_id, experiment_id, revision,
  content_json, hash, created_by, created_at
)

runs(
  run_id, experiment_id, title, status,
  actual_json, result, operator, run_at
)

deviations(
  deviation_id, run_id, field, planned, actual,
  reason, impact, corrective_action
)

data_refs(
  data_ref_id, experiment_id, run_id,
  path, host, protocol, checksum, data_class
)

signatures(
  signature_id, revision_id, signer,
  meaning, timestamp, hash, method
)

access_requests(
  request_id, experiment_id, requester,
  owner, scope, status, expires_at
)

audit_log(
  id, workspace_id, actor, action,
  object_type, object_id, old_value, new_value,
  reason, created_at
)
```

## 16. Migrating Existing Data

Existing:

- `protocol_imports`
- `protocol_steps`
- `experiment_runs`
- `experiment_run_files`

Migration:

1. Create a default project;
2. Bind runs to a project/experiment;
3. Legacy protocols become snapshots;
4. Legacy files become DataRefs or attachments;
5. Private by default;
6. Preserve original IDs;
7. Rollback is possible.

## 17. Phases

### P0: Projects and Designs
- project/design;
- Members/roles;
- Project page.

### P1: Protocol and Experiment
- Protocol snapshots;
- Local protocols;
- experiment/run;
- Planned vs. actual;
- Deviations.

### P2: Audit and Signatures
- revision;
- audit;
- e-signature;
- Locking;
- Export.

### P3: Access Requests
- PI request;
- member approve;
- Time limits/revocation;
- Audit.

### P4: DataRef and AI
- Path references;
- DSH calls;
- Experiment summaries;
- Design comparison.

### P5: Compliance Assessment
- If Part 11/GLP is required, validate separately.

## 18. Acceptance Criteria

- Every experiment references a protocol;
- Planned/actual deviations are recorded;
- Locked after signing;
- Revisions cannot be overwritten;
- The audit trail is complete;
- Members cannot see each other's records;
- PIs must request access;
- Private data never leaves the network;
- DataRefs resolve;
- Legacy runs can be migrated;
- Exports include the audit trail.

## 19. Risks

- Over-promising on compliance;
- Legal effect of electronic signatures;
- Mismatch between OS ACLs and ELN permissions;
- Broken paths;
- Protocol licensing;
- Project archiving policy;
- Audit data growth;
- Insufficient member collaboration.

## 20. Open Questions

1. Final compliance tier: B or A?
2. Is DSH on the user's desktop or on a server?
3. Is raw data on SMB/NFS/local?
4. Is there an OS ACL to align with?
5. Can a PI export after approval?
6. Does project closeout open access automatically?
7. Is a project template marketplace needed?
8. Are witness signatures needed?

## 21. Recommendation

```
Complete ELN
+ Project/Design/Protocol/Experiment/Run
+ planned vs. actual
+ Revision/Audit/E-signature
+ member-private
+ PI request–member approval
+ DataRef
+ local/HPC AI
+ B first, then evaluate A
```
