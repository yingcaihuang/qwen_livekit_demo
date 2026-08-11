# Design Document: UDP Monitoring Enhancement

## Architecture Overview

This feature extends the existing monitoring system with three new backend endpoints and a dedicated frontend page for UDP/WebRTC transport monitoring. The architecture follows the existing patterns established in `monitor.py` and `MonitorPage.tsx`.

### System Context

```
┌─────────────────────────────────────────────────────────────┐
│                   Frontend (React + TS)                       │
│  ┌──────────────┐     ┌─────────────────────────────────┐   │
│  │ MonitorPage  │────▶│      UdpMonitorPage             │   │
│  │  (existing)  │link │  /admin/monitor/udp             │   │
│  └──────────────┘     │  - WebRTC Stats Section         │   │
│                       │  - UDP Ports Section             │   │
│                       │  - TURN/STUN Section             │   │
│                       │  - Auto-refresh (10s)            │   │
│                       └─────────────┬───────────────────┘   │
└─────────────────────────────────────┼───────────────────────┘
                                      │ fetch (credentials: include)
                                      ▼
┌─────────────────────────────────────────────────────────────┐
│               Backend (FastAPI)                               │
│  router: /api/admin/monitor                                  │
│  ┌───────────────────┐ ┌──────────────┐ ┌───────────────┐  │
│  │ GET /webrtc-stats │ │GET /udp-ports│ │GET /turn-status│  │
│  └────────┬──────────┘ └──────┬───────┘ └───────┬───────┘  │
│           │                    │                  │          │
└───────────┼────────────────────┼──────────────────┼──────────┘
            │                    │                  │
            ▼                    ▼                  ▼
   ┌────────────────┐   ┌────────────────┐   ┌──────────┐
   │ LiveKit Server │   │  OS (ss -unap) │   │TCP socket│
   │  RoomService   │   │  /proc/net/udp │   │port 7881 │
   │    gRPC API    │   └────────────────┘   └──────────┘
   └────────────────┘
```

## Components

### Backend Components

#### 1. WebRTC Stats Endpoint (`GET /api/admin/monitor/webrtc-stats`)

Queries LiveKit RoomService to retrieve per-participant track statistics for all active rooms.

```python
@router.get("/webrtc-stats")
async def webrtc_stats(
    user: CurrentUser = Depends(require_permission("audit:read")),
) -> dict:
    """Return per-participant WebRTC track statistics grouped by room."""
    ...
```

**Implementation approach:**
1. Create LiveKitAPI instance using environment credentials (same pattern as `/rooms` endpoint).
2. Call `list_rooms()` to get all active rooms.
3. For each room, call `list_participants()` to get participant details.
4. For each participant, call `get_participant()` to retrieve track statistics.
5. Extract track-level RTP metrics (packet_loss, rtt, jitter, bitrate) and ICE info.
6. Group results by room name → participant identity → tracks.
7. On error, return `{ "rooms": [], "error": "<message>", "timestamp": "..." }`.

#### 2. UDP Port Status Endpoint (`GET /api/admin/monitor/udp-ports`)

Inspects system-level UDP socket state for ports 50000–50020.

```python
@router.get("/udp-ports")
async def udp_ports(
    user: CurrentUser = Depends(require_permission("audit:read")),
) -> dict:
    """Return UDP port binding status and packet counters for range 50000-50020."""
    ...
```

**Implementation approach:**
1. Execute `ss -unap` via `asyncio.create_subprocess_exec` to get UDP socket information.
2. Parse output to identify ports in range 50000–50020 that are bound.
3. For each bound port, extract recv/send queue sizes from `ss` output.
4. Fallback: If `ss` is unavailable, attempt to parse `/proc/net/udp` for hex-encoded port and queue data.
5. Report each port as `{ port: int, bound: bool, recv_queue: int, send_queue: int, recv_packets: int | null, send_packets: int | null }`.
6. On failure, return partial results with an error field.

#### 3. TURN/STUN Status Endpoint (`GET /api/admin/monitor/turn-status`)

Performs a TCP connectivity check to the TURN/STUN service on port 7881.

```python
@router.get("/turn-status")
async def turn_status(
    user: CurrentUser = Depends(require_permission("audit:read")),
) -> dict:
    """Check TURN/STUN service reachability on TCP port 7881."""
    ...
```

**Implementation approach:**
1. Resolve the LiveKit host from the `LIVEKIT_URL` environment variable.
2. Open a TCP socket with a 3-second timeout to `<host>:7881`.
3. Measure connection time as latency_ms.
4. Return `{ reachable: bool, latency_ms: int | null, timeout: bool, timestamp: str }`.

### Frontend Components

#### UdpMonitorPage (`/admin/monitor/udp`)

A new React page component following the same structure as `MonitorPage.tsx`.

```typescript
// frontend/src/pages/admin/UdpMonitorPage.tsx
export function UdpMonitorPage() { ... }
```

**Key behaviors:**
- Fetches all three endpoints in parallel via `Promise.all`.
- Auto-refreshes every 10 seconds using `setInterval`.
- Manual refresh button at top-right.
- Displays loading spinner while data is being fetched.
- Each section renders independently; if one endpoint fails, its section shows the error message while other sections continue rendering.

**Page layout (top to bottom):**
1. Header with title ("UDP/WebRTC 传输监控") + refresh button
2. TURN/STUN status card (compact summary)
3. WebRTC participant stats section (expandable table grouped by room → participant)
4. UDP port status section (grid of port cards showing bound/free + counters)

## Interfaces

### Backend API Response Types

#### WebRTC Stats Response

```python
{
    "rooms": [
        {
            "room_name": "session-abc123",
            "participants": [
                {
                    "identity": "user-xyz",
                    "ice_candidate_type": "host" | "srflx" | "relay",
                    "ice_connection_state": "connected" | "completed" | "disconnected" | ...,
                    "tracks": [
                        {
                            "track_type": "audio" | "video",
                            "direction": "publish" | "subscribe",
                            "packet_loss_ratio": 0.02,
                            "rtt_ms": 45.0,
                            "jitter_ms": 3.2,
                            "bitrate_kbps": 128.0
                        }
                    ]
                }
            ]
        }
    ],
    "error": null | "Error description",
    "timestamp": "2024-01-15T10:30:00.000Z"
}
```

#### UDP Ports Response

```python
{
    "ports": [
        {
            "port": 50000,
            "bound": true,
            "recv_queue": 0,
            "send_queue": 0,
            "recv_packets": 12345 | null,
            "send_packets": 6789 | null,
            "process": "livekit-server" | null
        }
    ],
    "port_range": {"start": 50000, "end": 50020},
    "error": null | "Error description",
    "timestamp": "2024-01-15T10:30:00.000Z"
}
```

#### TURN/STUN Status Response

```python
{
    "reachable": true,
    "latency_ms": 2,
    "timeout": false,
    "host": "livekit",
    "port": 7881,
    "timestamp": "2024-01-15T10:30:00.000Z"
}
```

### Frontend TypeScript Interfaces

```typescript
interface WebRtcStatsResponse {
  rooms: RoomStats[]
  error: string | null
  timestamp: string
}

interface RoomStats {
  room_name: string
  participants: ParticipantStats[]
}

interface ParticipantStats {
  identity: string
  ice_candidate_type: 'host' | 'srflx' | 'relay'
  ice_connection_state: string
  tracks: TrackStats[]
}

interface TrackStats {
  track_type: 'audio' | 'video'
  direction: 'publish' | 'subscribe'
  packet_loss_ratio: number
  rtt_ms: number
  jitter_ms: number
  bitrate_kbps: number
}

interface UdpPortsResponse {
  ports: UdpPortInfo[]
  port_range: { start: number; end: number }
  error: string | null
  timestamp: string
}

interface UdpPortInfo {
  port: number
  bound: boolean
  recv_queue: number
  send_queue: number
  recv_packets: number | null
  send_packets: number | null
  process: string | null
}

interface TurnStatusResponse {
  reachable: boolean
  latency_ms: number | null
  timeout: boolean
  host: string
  port: number
  timestamp: string
}
```

## Data Models

This feature operates entirely with in-memory snapshot data. No database tables or persistent storage are introduced. Each API request captures fresh data from the system and returns it directly.

**Data flow per request:**
1. Client sends GET request with auth cookie.
2. Backend validates JWT session + "audit:read" permission.
3. Backend queries the relevant data source (LiveKit gRPC / OS commands / TCP socket).
4. Backend constructs response with UTC timestamp.
5. Response returned to client (no caching layer).

## Error Handling

### Backend Error Strategy

| Scenario | Behavior |
|----------|----------|
| LiveKit unreachable | Return `{ rooms: [], error: "LiveKit RoomService unavailable: <detail>" }` |
| `ss` command not found | Fall back to `/proc/net/udp` parsing |
| Both `ss` and `/proc/net/udp` fail | Return `{ ports: [...partial], error: "System inspection failed: <detail>" }` |
| TURN port connection timeout (>3s) | Return `{ reachable: false, timeout: true, latency_ms: null }` |
| Unexpected exception in any endpoint | Catch at endpoint level, return structured error response (never 500) |
| Authentication failure | Standard 401/403 via `require_permission` dependency |

### Frontend Error Strategy

- Each section maintains its own error state.
- If `webrtc-stats` fails, that section shows an error message; UDP ports and TURN sections still render.
- Network failures (fetch rejected) display "网络错误" in the relevant section.
- Loading state shows a spinner per-section during initial load and a top-level spinner on first page load.

## Routing Integration

### Backend

All new endpoints are added to the existing `router` in `backend/app/api/monitor.py` (prefix `/api/admin/monitor`). No new router registration needed.

### Frontend

1. Add new route in `App.tsx`:
   ```tsx
   <Route path="/admin/monitor/udp" element={
     <ProtectedRoute capability="audit:read">
       <AppShell><UdpMonitorPage /></AppShell>
     </ProtectedRoute>
   } />
   ```

2. Add navigation link in `MonitorPage.tsx` header area pointing to `/admin/monitor/udp`.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

---

**Acceptance Criteria Testing Prework:**

1.1 WHEN an authenticated administrator requests WebRTC stats, THE UDP_Monitor_API SHALL query LiveKit_RoomService for all active rooms and return per-participant track statistics.
  Thoughts: This involves querying an external service (LiveKit). Testing the actual gRPC call is an integration concern. However, the data transformation logic (grouping by room/participant) is our code.
  Classification: INTEGRATION
  Test Strategy: Integration test with 1-2 examples using mocked LiveKit responses.

1.2 THE UDP_Monitor_API SHALL include RTP packet loss ratio, round-trip time in milliseconds, jitter in milliseconds, and bitrate in kbps for each audio and video track in the response.
  Thoughts: This is about response structure from our transformation layer. For any participant track data returned by LiveKit, our transformation must include all four metrics. We can generate random LiveKit participant data and verify the output always contains these fields.
  Classification: PROPERTY
  Test Strategy: Generate random LiveKit track data, verify transformation always includes all required metrics.

1.3 THE UDP_Monitor_API SHALL include the ICE candidate type (host, srflx, relay) and ICE connection state for each participant in the response.
  Thoughts: Similar to 1.2, this is about our data transformation ensuring ICE info is always present. Can be combined with 1.2 into a single property about response completeness.
  Classification: PROPERTY
  Test Strategy: Generate random participant data, verify ICE fields always present in output.

1.4 THE UDP_Monitor_API SHALL group the returned statistics by room name and participant identity.
  Thoughts: This is about our grouping logic. For any set of participant data across multiple rooms, the output structure must be organized by room → participant. We can test this is a property by generating random multi-room data.
  Classification: PROPERTY
  Test Strategy: Generate random multi-room participant data, verify correct grouping structure.

1.5 IF LiveKit_RoomService is unreachable or returns an error, THEN THE UDP_Monitor_API SHALL return an empty data set with an error message describing the failure reason.
  Thoughts: This is an error handling edge case. When the external service fails, our code must gracefully return an error structure.
  Classification: EDGE_CASE
  Test Strategy: Example test with mocked LiveKit failure, verify error response structure.

1.6 THE UDP_Monitor_API SHALL require the "audit:read" permission for access to the WebRTC stats endpoint.
  Thoughts: This is a one-time check that the endpoint has proper permission decoration. Running 100 times doesn't add value.
  Classification: SMOKE
  Test Strategy: Single test that unauthenticated/unauthorized request returns 401/403.

2.1 WHEN an authenticated administrator requests UDP port status, THE UDP_Monitor_API SHALL inspect system-level UDP socket information for the UDP_Port_Range (50000–50020).
  Thoughts: This calls an OS command (`ss`). The call itself is integration; but parsing the output is our code.
  Classification: INTEGRATION
  Test Strategy: Integration test with mocked subprocess output.

2.2 THE System_UDP_Inspector SHALL report which ports in the UDP_Port_Range are currently bound and which are free.
  Thoughts: This is our parsing logic. For any valid `ss` output, our parser must correctly identify bound vs free ports in the 50000-50020 range. The parser behavior varies meaningfully with different `ss` output formats.
  Classification: PROPERTY
  Test Strategy: Generate random `ss` output lines with various ports, verify correct bound/free classification.

2.3 THE System_UDP_Inspector SHALL report receive and transmit packet counts for each bound UDP port.
  Thoughts: This is about parsing counters from `ss` output. Can be combined with 2.2 as part of the same parsing property.
  Classification: PROPERTY
  Test Strategy: Generate random `ss` output with queue data, verify extraction.

2.4 THE System_UDP_Inspector SHALL report the receive and transmit buffer queue sizes for each bound UDP port.
  Thoughts: Same parsing logic as 2.3 — queue sizes come from the same `ss` output. Combine with 2.2/2.3.
  Classification: PROPERTY
  Test Strategy: Combined with 2.2/2.3.

2.5 IF the system-level inspection command fails or `/proc/net/udp` is not accessible, THEN THE UDP_Monitor_API SHALL return a partial result with an error message indicating the failure.
  Thoughts: Error handling edge case for when OS inspection fails.
  Classification: EDGE_CASE
  Test Strategy: Example test with simulated subprocess failure.

2.6 THE UDP_Monitor_API SHALL require the "audit:read" permission for access to the UDP port status endpoint.
  Thoughts: Same as 1.6, a smoke test for permission.
  Classification: SMOKE
  Test Strategy: Single test for 401/403.

3.1 WHEN an authenticated administrator requests TURN/STUN availability, THE UDP_Monitor_API SHALL perform a TCP connectivity check to the TURN_STUN_Service on port 7881.
  Thoughts: This is testing actual network connectivity to an external service.
  Classification: INTEGRATION
  Test Strategy: Integration test with mocked socket.

3.2 THE UDP_Monitor_API SHALL report the service reachability status (reachable or unreachable) and the connection latency in milliseconds.
  Thoughts: For any TCP connection result (success or failure), our code must always include both reachable status and latency. This is a data transformation property.
  Classification: PROPERTY
  Test Strategy: Generate random socket outcomes, verify response always contains both fields.

3.3 IF the TURN_STUN_Service connection attempt times out after 3 seconds, THEN THE UDP_Monitor_API SHALL report the service as unreachable with a timeout indicator.
  Thoughts: Specific timeout edge case.
  Classification: EDGE_CASE
  Test Strategy: Example test with simulated 3-second timeout.

3.4 THE UDP_Monitor_API SHALL require the "audit:read" permission for access to the TURN/STUN check endpoint.
  Thoughts: Smoke test for permission, same as 1.6/2.6.
  Classification: SMOKE
  Test Strategy: Single test for 401/403.

4.1 THE UDP_Monitor_Page SHALL be accessible via a navigation link from the existing Monitor page.
  Thoughts: UI presence test — check that a link exists.
  Classification: EXAMPLE
  Test Strategy: Render MonitorPage, verify link to /admin/monitor/udp exists.

4.2 THE UDP_Monitor_Page SHALL be routed under `/admin/monitor/udp` and require the "audit:read" capability for access.
  Thoughts: Route configuration check.
  Classification: SMOKE
  Test Strategy: Verify route is registered with correct capability.

4.3 THE UDP_Monitor_Page SHALL display WebRTC participant track statistics grouped by room and participant, showing packet loss, RTT, jitter, and bitrate for each track.
  Thoughts: For any valid WebRTC stats response, the rendered output must display all required metrics. We can generate random valid response data and verify the rendered component contains the expected values.
  Classification: PROPERTY
  Test Strategy: Generate random valid WebRTC stats, render component, verify all metrics displayed.

4.4 THE UDP_Monitor_Page SHALL display ICE candidate type and connection state for each participant.
  Thoughts: Similar to 4.3, rendering property. Can be combined with 4.3.
  Classification: PROPERTY
  Test Strategy: Combined with 4.3.

4.5 THE UDP_Monitor_Page SHALL display UDP port usage status for the port range 50000–50020, indicating bound and free ports with packet counters.
  Thoughts: For any valid UDP ports response, the UI must render port status correctly.
  Classification: PROPERTY
  Test Strategy: Generate random port data, verify rendering.

4.6 THE UDP_Monitor_Page SHALL display UDP socket buffer queue sizes for each bound port.
  Thoughts: Subset of 4.5, can be combined.
  Classification: PROPERTY
  Test Strategy: Combined with 4.5.

4.7 THE UDP_Monitor_Page SHALL display TURN/STUN service reachability status and latency.
  Thoughts: For any valid TURN status response, UI must show status and latency.
  Classification: EXAMPLE
  Test Strategy: Render with mock data, verify presence.

4.8 THE UDP_Monitor_Page SHALL provide a manual refresh button that fetches all monitoring data on demand.
  Thoughts: UI interaction test — click button, verify fetch called.
  Classification: EXAMPLE
  Test Strategy: Render, click refresh, verify fetch invocations.

4.9 THE UDP_Monitor_Page SHALL auto-refresh monitoring data every 10 seconds.
  Thoughts: Timer-based behavior — needs fake timers in test.
  Classification: EXAMPLE
  Test Strategy: Use fake timers, advance 10s, verify fetch called again.

4.10 WHILE monitoring data is loading, THE UDP_Monitor_Page SHALL display a loading indicator.
  Thoughts: UI state test.
  Classification: EXAMPLE
  Test Strategy: Render with pending fetch, verify loading indicator.

4.11 IF any API request fails, THEN THE UDP_Monitor_Page SHALL display the error message returned by the API within the relevant section without blocking other sections from rendering.
  Thoughts: For any combination of endpoint successes and failures, each section must render independently. This varies with input (which endpoints fail).
  Classification: PROPERTY
  Test Strategy: Generate random subsets of failing endpoints, verify only those sections show errors while others render data.

5.1 THE UDP_Monitor_API SHALL return fresh data from LiveKit_RoomService and System_UDP_Inspector on each request without caching or historical storage.
  Thoughts: This is an architectural constraint. We can verify no caching layer exists, but it's not a functional property we can test with random inputs.
  Classification: SMOKE
  Test Strategy: Call endpoint twice with different mock data, verify different results.

5.2 THE UDP_Monitor_API SHALL include a UTC timestamp in each response indicating when the snapshot was captured.
  Thoughts: For any response from any of the three endpoints, a timestamp field must be present and be a valid UTC datetime. This applies universally.
  Classification: PROPERTY
  Test Strategy: Call any endpoint, verify timestamp field is present and valid ISO 8601 UTC.

5.3 THE UDP_Monitor_API SHALL complete each monitoring request within 5 seconds under normal operating conditions.
  Thoughts: Performance requirement — not amenable to property testing.
  Classification: INTEGRATION
  Test Strategy: Integration test measuring response time under normal conditions.

---

**Property Reflection:**

Reviewing all identified properties for redundancy:

1. Properties 1.2 and 1.3 (response completeness for tracks and ICE) → **Combine** into one property: "WebRTC stats transformation includes all required fields."
2. Properties 2.2, 2.3, and 2.4 (parsing bound status, packet counts, queue sizes) → **Combine** into one property: "UDP port parser correctly extracts all metrics from ss output."
3. Properties 4.3 and 4.4 (display track stats and ICE info) → **Combine** into one property: "WebRTC stats section renders all required metrics."
4. Properties 4.5 and 4.6 (display port status and queue sizes) → **Combine** into one property: "UDP ports section renders all port metrics."
5. Property 5.2 (timestamp in response) is partially subsumed by testing individual endpoints, but it's a cross-cutting property that applies to all three endpoints, so it remains useful as a standalone property.

Final consolidated properties:

---

### Property 1: WebRTC stats response completeness

*For any* valid LiveKit participant track data, the WebRTC stats transformation SHALL produce a response where every track entry contains `packet_loss_ratio`, `rtt_ms`, `jitter_ms`, and `bitrate_kbps` fields, and every participant entry contains `ice_candidate_type` and `ice_connection_state` fields.

**Validates: Requirements 1.2, 1.3**

### Property 2: WebRTC stats grouping correctness

*For any* set of participants distributed across multiple rooms, the WebRTC stats response SHALL group participants under their respective room name, with no participant appearing under a room they do not belong to.

**Validates: Requirements 1.4**

### Property 3: UDP port parser extraction correctness

*For any* valid `ss -unap` output containing UDP socket entries in the port range 50000–50020, the parser SHALL correctly identify each port as bound, and extract the receive queue size and send queue size for each bound port. Ports in the range not present in the output SHALL be reported as free with zero queue sizes.

**Validates: Requirements 2.2, 2.3, 2.4**

### Property 4: TURN/STUN response structure completeness

*For any* TCP connection attempt result (success with measured latency, failure, or timeout), the TURN status response SHALL always contain a `reachable` boolean, a `latency_ms` value (number or null), and a `timeout` boolean field.

**Validates: Requirements 3.2, 3.3**

### Property 5: Frontend WebRTC section renders all metrics

*For any* valid WebRTC stats API response with at least one room and one participant, the rendered UDP Monitor Page SHALL display the packet loss ratio, RTT, jitter, bitrate, ICE candidate type, and ICE connection state for each participant's tracks.

**Validates: Requirements 4.3, 4.4**

### Property 6: Frontend UDP port section renders all port information

*For any* valid UDP ports API response, the rendered UDP Monitor Page SHALL display each port's bound/free status, and for bound ports SHALL show recv_queue, send_queue, and packet counters (when available).

**Validates: Requirements 4.5, 4.6**

### Property 7: Frontend section independence on partial failure

*For any* combination of API endpoint successes and failures (where at least one endpoint succeeds and at least one fails), the UDP Monitor Page SHALL render successful sections with their data and failed sections with their error messages, without any section blocking another.

**Validates: Requirements 4.11**

### Property 8: All API responses include valid UTC timestamp

*For any* successful or partial-error response from the webrtc-stats, udp-ports, or turn-status endpoints, the response SHALL contain a `timestamp` field with a valid ISO 8601 UTC datetime string representing the moment the snapshot was captured.

**Validates: Requirements 5.2**
