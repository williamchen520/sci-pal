# Work Plan: DSH Integration and Plugins

> Status: Pending review  
> Scope: Item 5 (DSH read-only tools, private/public entry points, static tokens, plugin UI, output gate, write operations, offline distribution)  
> Prerequisites: Item 3 domain packs, Item 4 multi-user and data classification.

## 1. Confirmed Decisions

| Item | Decision |
|---|---|
| First version | Read-only MCP |
| DSH UI | Phase 2 |
| Output hook | Implement it if available; no hard guarantee otherwise |
| Runtime location | DSH desktop first, server-side compatible |
| Private data | Local/HPC models only |
| Authentication | Static token |
| Write operations | Phase 2 |
| Offline bundle | Includes SciPal + integration package; DSH itself subject to license |

## 2. Overall Architecture

```
DSH desktop/server
   │ HTTPS / MCP
   ├─ scipal-public     data_class=public
   └─ scipal-private    data_class=internal/private/sealed
          │
       SciPal service
       ├─ permissions/workspace
       ├─ data classification
       ├─ retrieval/evidence
       ├─ digests/projects/ELN
       └─ audit
```

Principles:

```
DSH handles inference and the entry point
SciPal handles data, permissions, evidence, and audit
```

## 3. Two MCP Entry Points

### public

- Returns `public` only;
- Allows cloud DSH;
- Token scope `data_class=public`;
- Never returns private metadata.

### private

- May return `internal/private/sealed`;
- Local/HPC models only;
- Token scope `data_class=private`;
- Explicit administrator/user authorization.

Enforced server-side; never relies on client declarations.

## 4. Static Tokens

### Issuance

- Created in the SciPal web UI;
- Bound to user + workspace + data_class;
- Shown once, then only the hash is stored;
- Can be named, revoked, and given an expiry.

### Usage

```http
Authorization: Bearer <token>
```

### scope

```yaml
scopes:
  - evidence:read
  - brief:read
  - project:read
  - answer:validate
```

### Security

- TLS is mandatory;
- Tokens never appear in URLs;
- DSH stores them encrypted locally;
- Rotate regularly;
- Revocation takes effect immediately;
- Audit every call.

### Limitations

Static tokens are long-lived credentials:

- Higher leak risk than OAuth;
- Accepted for the first version;
- Can be upgraded to OIDC later.

## 5. Read-Only Tools

```text
scipal_search_evidence(query, top_k, data_class)
scipal_get_paper(paper_id)
scipal_get_brief(week)
scipal_get_project(project_id)
scipal_list_protocols(project_id)
scipal_validate_answer(answer, evidence_ids)
```

### search_evidence Returns

```json
{
  "evidence": [
    {
      "id": "P1",
      "paper_id": "...",
      "paragraph_id": "...",
      "sentence_ids": ["..."],
      "text": "...",
      "data_class": "public"
    }
  ],
  "sufficient": false,
  "allowed_citation_ids": ["P1"],
  "refusal_reason": "insufficient_evidence"
}
```

### Constraints

- Never return resources the token is not authorized for;
- Never return other workspaces;
- Never return private metadata to a public token;
- Digests are returned only to the owner;
- Projects return only metadata visible to members;
- ELN content is released per PI request / member approval.

## 6. DSH First Version

```
/scipal brief
→ returns a web URL
→ DSH opens it
```

- No cards;
- No embedding;
- No write operations;
- Read-only.

## 7. DSH Second Version

- Sidebar/cards;
- Evidence list;
- Digest items;
- Project entry point;
- Experiment record entry point;
- Citation click-through;
- Optional output validation.

## 8. Output Gate

If DSH provides a hook:

```
answer
→ scipal_validate_answer
→ unknown ids
→ uncited claims
→ reject/rewrite
```

If there is no hook:

```
No guarantee on the final answer
Formal Q&A goes through SciPal-first
```

Never force-block DSH output through the plugin.

## 9. Write Operations (Phase 2)

First batch:

```text
create_experiment_draft
add_note
create_brief_draft
link_paper
```

Requirements:

- Explicit user confirmation;
- Drafts only;
- No signing;
- No deletion;
- No approval;
- Audit;
- Permission checks;
- Cannot bypass PI/member rules.

## 10. Private Data Boundary

```
public DSH + public token
→ public only

local/HPC DSH + private token
→ internal/private/sealed
```

Server-side checks:

- token scope;
- workspace;
- data_class;
- resource ACL.

A cloud DSH should be blocked by administrators even if it obtains a private token;  
token issuance restricts data_class.

## 11. Identity

First version:

```
SciPal account
→ generate a static token
→ configure DSH
```

Later:

```
OIDC / device flow
```

PI/member permissions are still decided by SciPal.

## 12. Offline Bundle

```
scipal-offline-<version>.tar.gz
├─ SciPal images
├─ DSH integration package
├─ MCP config
├─ domain packs
├─ local model config
├─ checksums
└─ signatures
```

DSH itself:

- If the license permits, bundle the installer;
- Otherwise provide installation instructions and checksums;
- Never violate the DSH distribution license.

## 13. Evaluation

Comparison:

| Configuration | Description |
|---|---|
| SciPal QA | Baseline |
| DSH + public MCP | Read-only |
| DSH + private MCP | Local/HPC |
| DSH + validate | Strict gate |

Metrics:

- answer coverage;
- citation validity;
- refusal;
- private leak = 0;
- tool latency;
- token cost.

## 14. Phases

### P1: public Read-Only
- MCP server;
- Static token;
- search/get paper;
- URL digests;
- Audit.

### P2: private Read-Only
- private MCP;
- data_class;
- local/HPC DSH;
- digest/project tools.

### P3: DSH UI
- Cards;
- Sidebar;
- Citation click-through.

### P4: validate hook
- Output validation;
- Reject/rewrite.

### P5: Write Operations
- Draft experiments/notes/digests;
- Confirmation and audit.

### P6: Offline Bundle
- Integration package;
- Signatures;
- Install script.

## 15. Acceptance Criteria

- A public token cannot read private data;
- A private token works only for local/HPC;
- Cross-workspace access is rejected;
- Digests are returned only to the owner;
- PIs cannot use DSH to bypass the request flow;
- Tokens can be revoked;
- Auditing is complete;
- No private data leaves the network;
- Offline installation works.

## 16. Risks

- Static token leaks;
- DSH model location cannot be verified;
- Cloud DSH misusing a private token;
- Plugin output cannot be enforced;
- DSH licensing restricts distribution;
- MCP protocol changes;
- Tool calls amplifying permissions.

## 17. Open Questions

1. Does DSH provide an output hook?
2. Can the DSH desktop app configure multiple MCP servers?
3. May the offline package include the DSH installer?
4. Should private tokens be issuable only by administrators?
5. Should DSH display a "data class" badge?
6. Do write operations need a second-confirmation UI?

## 18. Recommendation

```
P1 public read-only MCP + URL
P2 private read-only + local/HPC
P3 DSH UI
P4 validate hook (if available)
P5 write operations, drafts
P6 offline bundle
```

In one sentence:

> DSH is the entry point and inference layer; SciPal uses tokens and MCP to control "what can be seen" and never hands permissions to the agent.
