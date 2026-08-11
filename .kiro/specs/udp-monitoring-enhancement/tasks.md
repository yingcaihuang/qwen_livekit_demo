# Implementation Plan: UDP Monitoring Enhancement

## Overview

Extend the existing monitoring system with three new backend API endpoints (WebRTC stats, UDP port status, TURN/STUN check) and a dedicated React frontend page at `/admin/monitor/udp`. The implementation follows existing patterns in `monitor.py` and `MonitorPage.tsx`, using Python/FastAPI for the backend and React/TypeScript/shadcn for the frontend.

## Tasks

- [x] 1. Implement backend WebRTC stats endpoint
  - [x] 1.1 Add `GET /api/admin/monitor/webrtc-stats` endpoint to `backend/app/api/monitor.py`
    - Create async function `webrtc_stats` with `require_permission("audit:read")` dependency
    - Instantiate `LiveKitAPI` using existing `_get_livekit_credentials()` helper and `LIVEKIT_URL` env var
    - Call `list_rooms()` then `list_participants()` for each room to get participant track statistics
    - Extract per-track RTP metrics: `packet_loss_ratio`, `rtt_ms`, `jitter_ms`, `bitrate_kbps`
    - Extract per-participant ICE info: `ice_candidate_type`, `ice_connection_state`
    - Group results by room name → participant identity → tracks
    - Include UTC timestamp in response
    - On LiveKit error, return `{ "rooms": [], "error": "<message>", "timestamp": "..." }`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 5.1, 5.2_

  - [ ]* 1.2 Write property test for WebRTC stats response completeness (Property 1)
    - **Property 1: WebRTC stats response completeness**
    - Generate random LiveKit participant/track data, pass through transformation logic
    - Verify every track entry contains `packet_loss_ratio`, `rtt_ms`, `jitter_ms`, `bitrate_kbps`
    - Verify every participant entry contains `ice_candidate_type` and `ice_connection_state`
    - **Validates: Requirements 1.2, 1.3**

  - [ ]* 1.3 Write property test for WebRTC stats grouping correctness (Property 2)
    - **Property 2: WebRTC stats grouping correctness**
    - Generate random sets of participants across multiple rooms
    - Verify participants are grouped under correct room names with no cross-contamination
    - **Validates: Requirements 1.4**

- [x] 2. Implement backend UDP port status endpoint
  - [x] 2.1 Add `GET /api/admin/monitor/udp-ports` endpoint to `backend/app/api/monitor.py`
    - Create async function `udp_ports` with `require_permission("audit:read")` dependency
    - Run `ss -unap` via `asyncio.create_subprocess_exec` and parse output for ports 50000–50020
    - For each port in range, report: `port`, `bound` (bool), `recv_queue`, `send_queue`, `recv_packets`, `send_packets`, `process`
    - Implement fallback to parse `/proc/net/udp` if `ss` is unavailable
    - Include `port_range: { start: 50000, end: 50020 }` and UTC timestamp in response
    - On failure, return partial results with `error` field
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 5.1, 5.2_

  - [ ]* 2.2 Write property test for UDP port parser extraction (Property 3)
    - **Property 3: UDP port parser extraction correctness**
    - Generate random `ss -unap` output lines with various ports in range 50000–50020
    - Verify parser correctly identifies bound ports, extracts recv/send queue sizes
    - Verify ports not present in output are reported as free with zero queue sizes
    - **Validates: Requirements 2.2, 2.3, 2.4**

- [x] 3. Implement backend TURN/STUN status endpoint
  - [x] 3.1 Add `GET /api/admin/monitor/turn-status` endpoint to `backend/app/api/monitor.py`
    - Create async function `turn_status` with `require_permission("audit:read")` dependency
    - Resolve LiveKit host from `LIVEKIT_URL` environment variable
    - Open TCP socket to `<host>:7881` with 3-second timeout using `asyncio.open_connection`
    - Measure connection latency in milliseconds
    - Return `{ reachable: bool, latency_ms: int|null, timeout: bool, host: str, port: 7881, timestamp: str }`
    - On timeout (>3s), return `{ reachable: false, timeout: true, latency_ms: null }`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.2_

  - [ ]* 3.2 Write property test for TURN/STUN response structure (Property 4)
    - **Property 4: TURN/STUN response structure completeness**
    - Generate random socket outcomes (success with latency, failure, timeout)
    - Verify response always contains `reachable` boolean, `latency_ms` (number or null), and `timeout` boolean
    - **Validates: Requirements 3.2, 3.3**

- [x] 4. Checkpoint - Backend endpoints complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement frontend UdpMonitorPage
  - [x] 5.1 Create TypeScript interfaces in `frontend/src/pages/admin/UdpMonitorPage.tsx`
    - Define `WebRtcStatsResponse`, `RoomStats`, `ParticipantStats`, `TrackStats` interfaces
    - Define `UdpPortsResponse`, `UdpPortInfo` interfaces
    - Define `TurnStatusResponse` interface
    - _Requirements: 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 5.2 Implement UdpMonitorPage component with data fetching and auto-refresh
    - Create `UdpMonitorPage` functional component following `MonitorPage.tsx` patterns
    - Fetch all three endpoints (`/webrtc-stats`, `/udp-ports`, `/turn-status`) in parallel via `Promise.all`
    - Implement auto-refresh every 10 seconds using `setInterval`
    - Provide manual refresh button in page header
    - Display loading indicator while data is being fetched
    - Each section maintains independent error state; one section's failure does not block others
    - _Requirements: 4.8, 4.9, 4.10, 4.11, 5.3_

  - [x] 5.3 Implement TURN/STUN status card section
    - Display compact summary card showing reachability status (reachable/unreachable)
    - Show connection latency in milliseconds when available
    - Show timeout indicator when applicable
    - Display target host and port
    - _Requirements: 4.7_

  - [x] 5.4 Implement WebRTC participant stats section
    - Display expandable table grouped by room → participant
    - For each track, show: track type (audio/video), direction, packet loss ratio, RTT, jitter, bitrate
    - For each participant, show: ICE candidate type, ICE connection state
    - Handle empty rooms list gracefully
    - _Requirements: 4.3, 4.4_

  - [x] 5.5 Implement UDP port status section
    - Display grid of port cards for range 50000–50020
    - Show bound/free status with visual indicator (color-coded)
    - Show recv_queue, send_queue for bound ports
    - Show packet counters (recv_packets, send_packets) when available
    - _Requirements: 4.5, 4.6_

- [x] 6. Register frontend route and add navigation link
  - [x] 6.1 Add route in `App.tsx` and navigation link in `MonitorPage.tsx`
    - Add import for `UdpMonitorPage` in `App.tsx`
    - Register route: `<Route path="/admin/monitor/udp" element={<ProtectedRoute capability="audit:read"><AppShell><UdpMonitorPage /></AppShell></ProtectedRoute>} />`
    - Add a navigation link/button in the `MonitorPage.tsx` header area pointing to `/admin/monitor/udp`
    - _Requirements: 4.1, 4.2_

- [x] 7. Checkpoint - Frontend integration complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Backend unit and integration tests
  - [ ]* 8.1 Write unit tests for WebRTC stats endpoint
    - Test with mocked LiveKit API returning multi-room data, verify response structure
    - Test LiveKit unreachable scenario returns `{ rooms: [], error: "..." }`
    - Test permission check returns 401/403 for unauthenticated requests
    - _Requirements: 1.1, 1.5, 1.6_

  - [ ]* 8.2 Write unit tests for UDP ports endpoint
    - Test with mocked `ss -unap` output, verify correct port parsing
    - Test fallback to `/proc/net/udp` when `ss` unavailable
    - Test subprocess failure returns partial result with error
    - _Requirements: 2.1, 2.2, 2.5_

  - [ ]* 8.3 Write unit tests for TURN/STUN status endpoint
    - Test successful connection with latency measurement
    - Test timeout scenario (>3s) returns `{ reachable: false, timeout: true }`
    - Test permission check returns 401/403
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ]* 8.4 Write property test for UTC timestamp across all endpoints (Property 8)
    - **Property 8: All API responses include valid UTC timestamp**
    - Call each endpoint with various mock scenarios
    - Verify every response contains `timestamp` field with valid ISO 8601 UTC datetime
    - **Validates: Requirements 5.2**

- [ ] 9. Frontend component tests (optional)
  - [ ]* 9.1 Write component tests for UdpMonitorPage rendering (Properties 5, 6, 7)
    - **Property 5: Frontend WebRTC section renders all metrics**
    - **Property 6: Frontend UDP port section renders all port information**
    - **Property 7: Frontend section independence on partial failure**
    - Test rendering with mock WebRTC stats data, verify all metrics displayed
    - Test rendering with mock UDP ports data, verify port status and counters shown
    - Test partial API failure scenario: one endpoint fails while others succeed
    - Verify failed section shows error, successful sections render data
    - **Validates: Requirements 4.3, 4.4, 4.5, 4.6, 4.11**

- [x] 10. Final checkpoint - All implementation complete
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend endpoints are added to the existing router in `backend/app/api/monitor.py` — no new router registration needed
- Frontend follows exact same patterns as existing `MonitorPage.tsx` for consistency

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "3.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.2", "3.2"] },
    { "id": 2, "tasks": ["5.1"] },
    { "id": 3, "tasks": ["5.2", "5.3", "5.4", "5.5"] },
    { "id": 4, "tasks": ["6.1"] },
    { "id": 5, "tasks": ["8.1", "8.2", "8.3", "8.4"] },
    { "id": 6, "tasks": ["9.1"] }
  ]
}
```
