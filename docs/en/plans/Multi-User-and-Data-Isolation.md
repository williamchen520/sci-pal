# Work Plan: Multi-User Support and Data Isolation

> Status: Pending review  
> Scope: Item 4 (multi-user support, permissions, data isolation, PI read-only/copy, LLM data boundaries)  
> Principles: Linux "everything is a file" + application-level VFS + data classification + local-first.

## 1. Background and Constraints

Lab scenario:

- Always-on Linux server;
- GPUs on servers/workstations;
- 20–30 people per research group;
- 1,000 accounts, about 100 concurrent;
- Private data never leaves the lab/institute network;
- Published literature may go to remote models;
- Some labs have an account system, some do not;
- Storage is server-local disks or external drives;
- No cross-lab sharing needed.

## 2. Goals

1. Multi-user, multi-workspace isolation;
2. PIs have read-only access to group-shared data;
3. PIs cannot read or copy private resources;
4. Sealed resources are completely invisible to PIs;
5. Route local/HPC/public-cloud models by data classification;
6. Start on a single node; support 1,000 accounts / 100 concurrent;
7. Support both standalone SciPal accounts and lab accounts.

## 3. Non-Goals

- Cross-lab sharing;
- Org charts / multi-level departments;
- Public-cloud SaaS multi-tenancy;
- Full LDAP/AD sync in v1;
- Kubernetes in v1.

## 4. Overall Architecture

```
Caddy / Nginx (TLS, rate limiting)
        │
Flask API (multiple workers)
        │
PostgreSQL (metadata, permissions, audit)
Redis (sessions, queues, rate limiting)
RQ/Celery workers (indexing, briefs, exports)
Chroma/Qdrant (vectors, workspace filtering)
MinIO / local content-addressed directory (files)
vLLM (local models)
LLM Gateway (local / HPC / public-cloud routing)
```

Start with single-node Docker Compose; size components for 100 concurrent users.

## 5. Identity and Authentication

### 5.1 Modes

```yaml
auth:
  mode: local | oidc | ldap | saml | hybrid
  allow_local_fallback: true
  group_mapping:
    lab_group: workspace_id
```

- `local`: standalone SciPal accounts;
- `oidc/saml`: lab-wide identity;
- `ldap`: AD/OpenLDAP;
- `hybrid`: external identity + local admin/service accounts.

### 5.2 Local Accounts

- Argon2id password hashing;
- Unique email/username;
- First admin created during deployment initialization;
- Users are not mapped to Linux system users.

### 5.3 Sessions and Tokens

- Redis sessions;
- Short-lived access tokens;
- MCP/DSH use scoped API tokens;
- Tokens are bound to user + workspace;
- Revocable.

### 5.4 Account Scale

- 1,000 accounts;
- 100 concurrent;
- SSO preferred;
- Local accounts are a fallback only.

## 6. Multi-Tenancy Model

```
Organization (optional)
└─ Workspace (research group)
   ├─ Membership(role)
   ├─ Project
   ├─ Experiment
   ├─ Brief
   └─ Resource
```

- `workspace` is the unit of isolation;
- A user can belong to multiple workspaces;
- No sharing across workspaces;
- Only the global `public` paper library is shared.

### Roles

| Role | Permissions |
|---|---|
| owner | Manage the workspace, members, configuration, and deletion |
| PI | Read internal/public; copy internal/public; cannot write others' resources |
| member | Read/write own resources; read shared projects |
| viewer | Read-only access to shared content |
| admin | System configuration/backup/audit; does not read business data by default |

## 7. Data Classification

Each resource:

```text
data_class = public | internal | private | sealed
source     = published | unpublished | experiment | note | brief
license    = ...
```

| Class | Example | PI read | PI copy | Public-cloud model |
|---|---|---|---|---|
| public | Published papers | ✅ | ✅ | ✅ |
| internal | Group-shared | ✅ | ✅ | ❌ |
| private | Raw experiment data | ❌ | ❌ | ❌ |
| sealed | Notes, brief drafts | ❌ | ❌ | ❌ |

### private

Visible to the PI:

- That the resource exists;
- Type;
- Size;
- Modification time;
- hash/version changes.

Not visible to the PI:

- Content;
- Sensitive fields beyond the filename;
- Not copyable.

### sealed

The PI cannot see even existence or modification.  
Only the owner can see it.

### Member-Initiated Sharing

Only the owner can share private/sealed resources:

```
share / transfer
→ create a copy or grant authorization
→ only then can the PI read/copy
```

PIs may not blindly copy resources on their own.

## 8. Logical VFS

```text
/scipal
├─ library/                  # public, read-only
├─ workspaces/<ws>/
│  ├─ shared/                # internal
│  ├─ members/<user>/        # private
│  ├─ projects/
│  ├─ experiments/
│  ├─ briefs/
│  └─ pi/
├─ users/<user>/private/     # sealed/private
├─ etc/                      # system configuration, not visible to business users
├─ var/                      # indexes/cache/jobs/audit, not visible to business users
└─ proc/                     # runtime state, not visible to business users
```

### Business-Visible Scope

Expose only allowlisted resources:

- paper
- project
- experiment
- brief
- note
- attachment

`/etc`, `/var`, and `/proc` are completely invisible to business users.

### No Arbitrary Path Operations

- No `cp /any/path`;
- Copy accepts resource IDs only;
- The server resolves resource paths;
- Reject `..`, absolute paths, and cross-workspace paths;
- Symbolic links are not used as permission boundaries.

### xattr

```text
owner
workspace
data_class
source
license
hash
copied_from
```

## 9. Copying and Unlocking

### Copyable

Only:

- public;
- internal;
- private resources already shared/transferred by the owner.

### Copy Semantics

```
POST /api/resources/<id>/copy
target = personal directory or a specified project
→ the server deep-copies metadata + content
→ record source_resource_id
→ new resource owner = the acting user
→ preserve data_class and license
→ write an audit entry
```

### PI Copies

- PIs can copy internal/public;
- The copy belongs to the PI and is editable;
- The original is unchanged;
- Cannot copy private/sealed.

## 10. LLM Gateway and Data Boundaries

### 10.1 Endpoint Registration

```yaml
providers:
  - id: local-vllm
    trust_zone: onprem
  - id: hpc-llm
    trust_zone: hpc
  - id: deepseek
    trust_zone: public_cloud
```

### 10.2 Routing Matrix

| data_class | local | hpc | public_cloud |
|---|---|---|---|
| public | ✅ | ✅ | ✅ |
| internal | ✅ | ✅ | ❌ |
| private | ✅ | ✅ | ❌ |
| sealed | ✅ | ✅ | ❌ |

### 10.3 Rules

- Evidence containing private/sealed/internal data → onprem/hpc only;
- No local/HPC model available → return evidence only, do not generate conclusions;
- No silent fallback to the public cloud;
- Log the policy decision for every call;
- Copies/derivatives inherit the highest data_class.

### 10.4 Public-Cloud APIs

- Handle public papers only;
- Do not send project names, experiment records, notes, or brief drafts;
- Check at the resource level before sending, not just the query.

## 11. Storage

### Metadata

PostgreSQL:

- users
- workspaces
- memberships
- resources
- resource_acl
- resource_copies
- audit_log

### Files

```
/data/scipal/
  blobs/<sha256>
  workspaces/<ws>/
  backups/
```

- Content-addressed;
- Local disk or external drive;
- No NAS dependency;
- The service account reads/writes; business users never access files directly.

### Backups

- restic / pg_dump;
- Daily incremental;
- Local + external drive;
- Encrypted;
- Periodic restore drills.

## 12. Data Model (Core Tables)

```sql
users(user_id, username, email, password_hash, status, created_at)

workspaces(workspace_id, name, owner_user_id, created_at)

memberships(workspace_id, user_id, role, status)

resources(
  resource_id, workspace_id, owner_user_id,
  resource_type, name, data_class, visibility,
  storage_key, hash, size, mtime, created_at
)

resource_acl(
  resource_id, subject_type, subject_id, permission
)

resource_copies(
  copy_id, source_resource_id, target_resource_id,
  copied_by, copied_at
)

audit_log(
  id, workspace_id, actor_user_id, action,
  resource_id, metadata, created_at
)
```

## 13. Isolation Implementation

### Database

- Every query is forced to include `workspace_id`;
- Injected centrally at the repository layer;
- PostgreSQL RLS (phase 2);
- Routes must not build SQL directly.

### Vector Store

- Single collection + `workspace_id` metadata;
- Every query is forced through a filter;
- Negative tests: no cross-workspace hits;
- Enterprise edition may use separate collections.

### Cache

- Keys include user/workspace;
- No reuse across workspaces.

### Files

- Paths are generated server-side;
- Business APIs never accept raw paths;
- Downloads go through authenticated endpoints.

## 14. Audit

Record:

- Logins/failures;
- PI reads of internal/public;
- Member share/transfer;
- Copies;
- Exports;
- Deletions;
- Permission changes;
- LLM policy decisions.

private:

- Record that the PI viewed metadata;
- Do not record content;
- Do not record PI content reads (they cannot read it anyway).

sealed:

- Produce no audit visible to the PI.

Audit visibility for members:

```
Members can see when "their resource's metadata was viewed by a PI / was shared / was copied"
```

## 15. Migration

Existing single-user data:

1. Create a default workspace;
2. Assign existing data to the owner;
3. Backfill `workspace_id`;
4. Map legacy APIs to the default workspace;
5. Migration script is reversible;
6. Back up before migrating.

Existing cloud configuration:

- Applies to public data only by default;
- private data must use local/HPC;
- Validate provider configuration at startup; refuse to start or disable the cloud if it is non-compliant.

## 16. Phases

### P0: Identity and Tenancy
- Local accounts;
- workspace/roles;
- First admin;
- Single-user migration.

### P1: VFS and Permissions
- Resource tables;
- Allowlisted resources;
- PI read-only;
- private/sealed semantics;
- Copy/share;
- Audit.

### P2: Data Classification and LLM Gateway
- data_class;
- provider trust_zone;
- policy router;
- Block private data from leaving the network;
- Logging.

### P3: Scale
- PostgreSQL;
- Redis/RQ;
- Multiple workers;
- Object storage/external drive;
- 100-concurrent load test;
- Import 1,000 accounts.

### P4: SSO and Operations
- OIDC/LDAP;
- Backup and restore;
- Monitoring and alerting;
- Admin UI.

## 17. Acceptance

### Isolation

- User A cannot read user B's private resources;
- Members cannot read others' private resources;
- PIs cannot read/copy private resources;
- PIs cannot see sealed resources;
- Cross-workspace queries return empty;
- Vector search does not cross workspaces.

### Permissions

- PIs can read internal/public;
- PIs cannot write others' resources;
- Copying internal/public unlocks it for the PI;
- After a member shares, the PI can read.

### Data Boundaries

- private requests never call public_cloud;
- Without a local/HPC model, only evidence is returned;
- Policy decisions are audited.

### Scale

- 1,000 accounts;
- 100-concurrent smoke test;
- Acceptable API P95;
- The indexing queue does not block queries.

## 18. Risks

- private metadata may still leak information;
- A missing Chroma filter leads to privilege escalation;
- SQLite is unusable with multiple workers; PostgreSQL is required;
- External drive failure;
- Insufficient local model capability;
- HPC endpoint trust boundary;
- Abuse of the PI sharing workflow;
- Unencrypted backups.

## 19. Open Questions

1. Preferred SSO protocol: OIDC or LDAP?
2. Does an HPC model endpoint already exist, and who maintains it?
3. Server GPU memory, which determines local model size;
4. External drive capacity and backup drive;
5. What granularity of private metadata is shown to PIs;
6. Whether member shares require PI confirmation;
7. Whether 100 concurrent is a peak or the norm.

## 20. Recommendation

```
Linux on-prem
+ PostgreSQL/Redis
+ logical VFS
+ workspace isolation
+ PI read-only on internal/public
+ private unreadable/uncopyable
+ sealed invisible
+ data classification + LLM gateway
+ start single-node, 1,000 accounts/100 concurrent
```
