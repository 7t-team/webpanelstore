# Execution Flow Diagrams

## 1. Complete System Flow

```
┌─────────────┐
│    User     │
└──────┬──────┘
       │ 1. Browse apps
       ▼
┌─────────────────────────────────────────┐
│         Web Panel (Flask)               │
│                                         │
│  ┌────────────────────────────────┐   │
│  │   Manifest Registry            │   │
│  │   - Loads all manifests        │   │
│  │   - Caches in memory           │   │
│  └────────────────────────────────┘   │
│                                         │
│  2. User selects app                   │
│     ↓                                   │
│  ┌────────────────────────────────┐   │
│  │   Dynamic Form Generator       │   │
│  │   - Reads manifest inputs      │   │
│  │   - Generates HTML form        │   │
│  │   - Handles conditional fields │   │
│  └────────────────────────────────┘   │
│                                         │
│  3. User submits form                  │
│     ↓                                   │
│  ┌────────────────────────────────┐   │
│  │   Input Validator              │   │
│  │   - Type checking              │   │
│  │   - Pattern matching           │   │
│  │   - Range validation           │   │
│  │   - Required fields            │   │
│  └────────────────────────────────┘   │
│                                         │
│  4. Validation passes                  │
│     ↓                                   │
│  ┌────────────────────────────────┐   │
│  │   Job Manager                  │   │
│  │   - Creates job ID             │   │
│  │   - Signs with HMAC            │   │
│  │   - Stores metadata            │   │
│  └────────────────────────────────┘   │
└──────────────┬──────────────────────────┘
               │ 5. Push to queue
               ▼
        ┌──────────────┐
        │    Redis     │
        │  Job Queue   │
        └──────┬───────┘
               │ 6. Agent polls
               ▼
┌─────────────────────────────────────────┐
│      Agent Daemon (systemd)             │
│                                         │
│  ┌────────────────────────────────┐   │
│  │   Job Poller                   │   │
│  │   - BLPOP from queue           │   │
│  │   - Receives job JSON          │   │
│  └────────────────────────────────┘   │
│                                         │
│  7. Validate job                       │
│     ↓                                   │
│  ┌────────────────────────────────┐   │
│  │   Security Layer               │   │
│  │   - Verify HMAC signature      │   │
│  │   - Check whitelist            │   │
│  │   - Validate inputs            │   │
│  └────────────────────────────────┘   │
│                                         │
│  8. Execute installer                  │
│     ↓                                   │
│  ┌────────────────────────────────┐   │
│  │   Execution Engine             │   │
│  │   - Load manifest              │   │
│  │   - Prepare environment        │   │
│  │   - Execute script             │   │
│  │   - Capture output             │   │
│  │   - Monitor timeout            │   │
│  └────────────────────────────────┘   │
│                                         │
│  9. Publish result                     │
│     ↓                                   │
│  ┌────────────────────────────────┐   │
│  │   State Manager                │   │
│  │   - Store result               │   │
│  │   - Publish to Redis           │   │
│  │   - Update job status          │   │
│  └────────────────────────────────┘   │
└──────────────┬──────────────────────────┘
               │ 10. Result available
               ▼
        ┌──────────────┐
        │    Redis     │
        │   Results    │
        └──────┬───────┘
               │ 11. User polls
               ▼
┌─────────────────────────────────────────┐
│         Web Panel (Flask)               │
│  - Returns job status                   │
│  - Shows logs                           │
│  - Displays result                      │
└─────────────────────────────────────────┘
```

## 2. Installer Execution Flow

```
┌─────────────────────────────────────────┐
│         Agent Receives Job              │
└──────────────┬──────────────────────────┘
               │
               ▼
        ┌──────────────┐
        │ Verify HMAC  │
        │  Signature   │
        └──────┬───────┘
               │ Valid?
               ├─── No ──→ [Reject Job]
               │
               ▼ Yes
        ┌──────────────┐
        │Check Manifest│
        │   Exists?    │
        └──────┬───────┘
               │ Exists?
               ├─── No ──→ [Reject Job]
               │
               ▼ Yes
        ┌──────────────┐
        │ Load Manifest│
        │   (YAML)     │
        └──────┬───────┘
               │
               ▼
        ┌──────────────┐
        │  Validate    │
        │   Inputs     │
        └──────┬───────┘
               │ Valid?
               ├─── No ──→ [Return Error]
               │
               ▼ Yes
        ┌──────────────┐
        │   Convert    │
        │ to Env Vars  │
        └──────┬───────┘
               │
               ▼
        ┌──────────────────────────────┐
        │  Execute install.sh          │
        │                              │
        │  ┌────────────────────────┐ │
        │  │ set -euo pipefail      │ │
        │  │                        │ │
        │  │ # Read env vars        │ │
        │  │ SERVER_NAME=$SERVER_NAME│ │
        │  │                        │ │
        │  │ # Install              │ │
        │  │ apt-get install -y -qq │ │
        │  │                        │ │
        │  │ # Configure            │ │
        │  │ cat > /etc/config      │ │
        │  │                        │ │
        │  │ # Validate             │ │
        │  │ service-test || exit 3 │ │
        │  │                        │ │
        │  │ # Start service        │ │
        │  │ systemctl start app    │ │
        │  │                        │ │
        │  │ exit 0                 │ │
        │  └────────────────────────┘ │
        └──────────────┬───────────────┘
                       │
                       ▼
                ┌──────────────┐
                │ Capture Exit │
                │     Code     │
                └──────┬───────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼ 0            ▼ 1            ▼ 2,3
   ┌─────────┐   ┌─────────┐   ┌─────────┐
   │ Success │   │Validation│   │ Failed  │
   │         │   │  Error   │   │         │
   └────┬────┘   └────┬────┘   └────┬────┘
        │             │             │
        └─────────────┼─────────────┘
                      │
                      ▼
              ┌───────────────┐
              │ Store Result  │
              │  in Redis     │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ Publish Event │
              │  (PubSub)     │
              └───────────────┘
```

## 3. Security Validation Flow

```
┌─────────────────────────────────────────┐
│         Job Arrives at Agent            │
└──────────────┬──────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────┐
│         Layer 1: Signature               │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │ Extract signature from job         │ │
│  │ Compute HMAC-SHA256 of payload     │ │
│  │ Compare with received signature    │ │
│  └────────────────────────────────────┘ │
└──────────────┬───────────────────────────┘
               │ Valid?
               ├─── No ──→ [REJECT: Invalid signature]
               │
               ▼ Yes
┌──────────────────────────────────────────┐
│         Layer 2: Whitelist               │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │ Check if app_id exists in          │ │
│  │ /opt/provisioning/installers/      │ │
│  │ Verify manifest.yml exists         │ │
│  └────────────────────────────────────┘ │
└──────────────┬───────────────────────────┘
               │ Exists?
               ├─── No ──→ [REJECT: Not whitelisted]
               │
               ▼ Yes
┌──────────────────────────────────────────┐
│         Layer 3: Input Validation        │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │ For each input field:              │ │
│  │   - Check required fields          │ │
│  │   - Validate type                  │ │
│  │   - Check pattern (regex)          │ │
│  │   - Verify length/range            │ │
│  │   - Check allowed_values           │ │
│  └────────────────────────────────────┘ │
└──────────────┬───────────────────────────┘
               │ Valid?
               ├─── No ──→ [REJECT: Invalid inputs]
               │
               ▼ Yes
┌──────────────────────────────────────────┐
│         Layer 4: Path Validation         │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │ Verify script path is safe         │ │
│  │ No path traversal (../)            │ │
│  │ Script must be .sh file            │ │
│  └────────────────────────────────────┘ │
└──────────────┬───────────────────────────┘
               │ Safe?
               ├─── No ──→ [REJECT: Unsafe path]
               │
               ▼ Yes
┌──────────────────────────────────────────┐
│         Layer 5: Sandboxing              │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │ Create new process group           │ │
│  │ Set timeout from manifest          │ │
│  │ Limit environment variables        │ │
│  │ Capture stdout/stderr              │ │
│  └────────────────────────────────────┘ │
└──────────────┬───────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────┐
│         Layer 6: Execution               │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │ Execute with subprocess.Popen      │ │
│  │ Monitor for timeout                │ │
│  │ Kill on timeout (SIGTERM/SIGKILL)  │ │
│  │ Capture exit code                  │ │
│  └────────────────────────────────────┘ │
└──────────────┬───────────────────────────┘
               │
               ▼
        [Script Executes]
```

## 4. Manifest to Form Flow

```
┌─────────────────────────────────────────┐
│         installers/nginx/               │
│         manifest.yml                    │
│                                         │
│  inputs:                                │
│    - name: server_name                  │
│      type: string                       │
│      label: Server Name                 │
│      required: true                     │
│      validation:                        │
│        pattern: '^[a-z0-9\-\.]+$'       │
│                                         │
│    - name: enable_ssl                   │
│      type: boolean                      │
│      label: Enable SSL                  │
│      default: "true"                    │
│                                         │
│    - name: https_port                   │
│      type: port                         │
│      label: HTTPS Port                  │
│      visible_if:                        │
│        enable_ssl: "true"               │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│      Panel: Manifest Registry           │
│      - Loads YAML                       │
│      - Parses inputs                    │
│      - Caches in memory                 │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│      Panel: Form Generator              │
│                                         │
│  For each input:                        │
│    1. Read type                         │
│    2. Generate HTML element             │
│    3. Add validation attributes         │
│    4. Handle conditional visibility     │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│         Generated HTML Form             │
│                                         │
│  <form>                                 │
│    <label>Server Name *</label>         │
│    <input type="text"                   │
│           name="server_name"            │
│           required                      │
│           pattern="^[a-z0-9\-\.]+$">    │
│                                         │
│    <label>Enable SSL</label>            │
│    <select name="enable_ssl">           │
│      <option value="true">Yes</option>  │
│      <option value="false">No</option>  │
│    </select>                            │
│                                         │
│    <div id="ssl_fields"                 │
│         style="display:none">           │
│      <label>HTTPS Port</label>          │
│      <input type="number"               │
│             name="https_port"           │
│             min="1" max="65535">        │
│    </div>                               │
│                                         │
│    <button type="submit">Install</button>│
│  </form>                                │
│                                         │
│  <script>                               │
│    // Show/hide conditional fields      │
│    enable_ssl.onchange = () => {        │
│      ssl_fields.style.display =         │
│        enable_ssl.value === 'true'      │
│          ? 'block' : 'none';            │
│    };                                   │
│  </script>                              │
└─────────────────────────────────────────┘
```

## 5. Error Handling Flow

```
┌─────────────────────────────────────────┐
│         Script Execution                │
└──────────────┬──────────────────────────┘
               │
               ▼
        ┌──────────────┐
        │  Exit Code   │
        └──────┬───────┘
               │
    ┌──────────┼──────────┬──────────┐
    │          │          │          │
    ▼ 0        ▼ 1        ▼ 2        ▼ 3
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│ Success │ │Validation│ │Install  │ │ Config  │
│         │ │  Error   │ │  Error  │ │  Error  │
└────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
     │           │           │           │
     │           │           │           │
     ▼           ▼           ▼           ▼
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│ Return  │ │ Return  │ │  Retry  │ │ Return  │
│ Success │ │  Error  │ │  Logic  │ │  Error  │
│         │ │         │ │         │ │         │
│ No      │ │ No      │ │ Yes     │ │ No      │
│ Retry   │ │ Retry   │ │ Retry   │ │ Retry   │
└─────────┘ └─────────┘ └────┬────┘ └─────────┘
                              │
                              ▼
                       ┌──────────────┐
                       │ Retry Logic  │
                       │              │
                       │ Attempt 1:   │
                       │   Wait 10s   │
                       │              │
                       │ Attempt 2:   │
                       │   Wait 20s   │
                       │              │
                       │ Attempt 3:   │
                       │   Wait 40s   │
                       │              │
                       │ Max reached: │
                       │   Give up    │
                       └──────────────┘
```

## 6. Data Flow

```
User Input → Validation → Job Creation → Queue → Agent → Execution → Result

┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  User    │   │  Panel   │   │  Redis   │   │  Agent   │   │ Installer│
└────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘
     │              │              │              │              │
     │ POST /install│              │              │              │
     ├─────────────>│              │              │              │
     │              │              │              │              │
     │              │ Validate     │              │              │
     │              │ inputs       │              │              │
     │              │              │              │              │
     │              │ Create job   │              │              │
     │              │ + HMAC       │              │              │
     │              │              │              │              │
     │              │ RPUSH job    │              │              │
     │              ├─────────────>│              │              │
     │              │              │              │              │
     │ 201 Created  │              │              │              │
     │ {job_id}     │              │              │              │
     │<─────────────┤              │              │              │
     │              │              │              │              │
     │              │              │ BLPOP job    │              │
     │              │              │<─────────────┤              │
     │              │              │              │              │
     │              │              │ Return job   │              │
     │              │              ├─────────────>│              │
     │              │              │              │              │
     │              │              │              │ Verify HMAC  │
     │              │              │              │              │
     │              │              │              │ Validate     │
     │              │              │              │              │
     │              │              │              │ Execute      │
     │              │              │              ├─────────────>│
     │              │              │              │              │
     │              │              │              │              │ Run
     │              │              │              │              │ script
     │              │              │              │              │
     │              │              │              │ Exit code    │
     │              │              │              │<─────────────┤
     │              │              │              │              │
     │              │              │ SET result   │              │
     │              │              │<─────────────┤              │
     │              │              │              │              │
     │ GET /jobs/id │              │              │              │
     ├─────────────>│              │              │              │
     │              │              │              │              │
     │              │ GET result   │              │              │
     │              ├─────────────>│              │              │
     │              │              │              │              │
     │              │ Return result│              │              │
     │              │<─────────────┤              │              │
     │              │              │              │              │
     │ 200 OK       │              │              │              │
     │ {result}     │              │              │              │
     │<─────────────┤              │              │              │
     │              │              │              │              │
```

## 7. Idempotency Pattern

```
┌─────────────────────────────────────────┐
│         install.sh Execution            │
└──────────────┬──────────────────────────┘
               │
               ▼
        ┌──────────────┐
        │ Check if     │
        │ already      │
        │ installed    │
        └──────┬───────┘
               │
        ┌──────┴──────┐
        │             │
        ▼ Yes         ▼ No
┌──────────────┐ ┌──────────────┐
│ Log: Already │ │ Log: Fresh   │
│ installed    │ │ installation │
└──────┬───────┘ └──────┬───────┘
       │                │
       ▼                ▼
┌──────────────┐ ┌──────────────┐
│ Update       │ │ Full         │
│ config only  │ │ installation │
└──────┬───────┘ └──────┬───────┘
       │                │
       └────────┬───────┘
                │
                ▼
         ┌──────────────┐
         │ Configure    │
         │ service      │
         └──────┬───────┘
                │
                ▼
         ┌──────────────┐
         │ Reload/      │
         │ Restart      │
         │ service      │
         └──────┬───────┘
                │
                ▼
         ┌──────────────┐
         │ Verify       │
         │ running      │
         └──────┬───────┘
                │
                ▼
         ┌──────────────┐
         │ Exit 0       │
         │ (Success)    │
         └──────────────┘

Example Code:

if command -v nginx &> /dev/null; then
    log "Already installed"
    SKIP_INSTALL=true
else
    SKIP_INSTALL=false
fi

if [[ "$SKIP_INSTALL" == "false" ]]; then
    apt-get install -y nginx
fi

# Always update config
cat > /etc/nginx/nginx.conf <<EOF
...
EOF

# Always reload
systemctl reload nginx
```

---

These diagrams illustrate the complete execution flow from user interaction through to successful installation, showing all security layers, validation steps, and error handling paths.
