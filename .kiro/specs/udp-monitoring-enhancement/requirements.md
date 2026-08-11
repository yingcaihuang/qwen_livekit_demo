# Requirements Document

## Introduction

Enhance the existing system monitoring module to provide comprehensive UDP and WebRTC transport monitoring capabilities. The feature adds a dedicated sub-page accessible from the current Monitor page, offering real-time snapshots of WebRTC transport quality metrics (via LiveKit RoomService API) and system-level UDP port status (via OS-level inspection). All data is fetched on demand without historical persistence.

## Glossary

- **UDP_Monitor_API**: The FastAPI backend router responsible for exposing UDP/WebRTC monitoring endpoints under the `/api/admin/monitor` prefix.
- **UDP_Monitor_Page**: The React frontend page that renders UDP port status and WebRTC transport quality data, accessible from the existing Monitor page.
- **LiveKit_RoomService**: The LiveKit server-side API used to query room participant track statistics including packet loss, RTT, jitter, and bitrate.
- **System_UDP_Inspector**: The backend component that reads OS-level UDP socket information from `ss` command output or `/proc/net/udp` to determine port binding and packet counters.
- **Participant_Track_Stats**: Per-participant, per-track statistics retrieved from LiveKit RoomService, including RTP packet loss ratio, round-trip time, jitter, and bitrate for audio and video tracks.
- **UDP_Port_Range**: The configured LiveKit UDP RTC port range of 50000–50020 used for WebRTC media transport.
- **TURN_STUN_Service**: The built-in TURN/STUN service on LiveKit TCP port 7881 that provides NAT traversal for WebRTC clients.

## Requirements

### Requirement 1: WebRTC Participant Track Statistics Endpoint

**User Story:** As an administrator, I want to view per-participant WebRTC track statistics for all active rooms, so that I can diagnose audio/video quality issues in real time.

#### Acceptance Criteria

1. WHEN an authenticated administrator requests WebRTC stats, THE UDP_Monitor_API SHALL query LiveKit_RoomService for all active rooms and return per-participant track statistics.
2. THE UDP_Monitor_API SHALL include RTP packet loss ratio, round-trip time in milliseconds, jitter in milliseconds, and bitrate in kbps for each audio and video track in the response.
3. THE UDP_Monitor_API SHALL include the ICE candidate type (host, srflx, relay) and ICE connection state for each participant in the response.
4. THE UDP_Monitor_API SHALL group the returned statistics by room name and participant identity.
5. IF LiveKit_RoomService is unreachable or returns an error, THEN THE UDP_Monitor_API SHALL return an empty data set with an error message describing the failure reason.
6. THE UDP_Monitor_API SHALL require the "audit:read" permission for access to the WebRTC stats endpoint.

### Requirement 2: System-Level UDP Port Status Endpoint

**User Story:** As an administrator, I want to see the current state of UDP ports in the RTC range (50000–50020), so that I can verify media transport ports are properly allocated and functioning.

#### Acceptance Criteria

1. WHEN an authenticated administrator requests UDP port status, THE UDP_Monitor_API SHALL inspect system-level UDP socket information for the UDP_Port_Range (50000–50020).
2. THE System_UDP_Inspector SHALL report which ports in the UDP_Port_Range are currently bound and which are free.
3. THE System_UDP_Inspector SHALL report receive and transmit packet counts for each bound UDP port.
4. THE System_UDP_Inspector SHALL report the receive and transmit buffer queue sizes for each bound UDP port.
5. IF the system-level inspection command fails or `/proc/net/udp` is not accessible, THEN THE UDP_Monitor_API SHALL return a partial result with an error message indicating the failure.
6. THE UDP_Monitor_API SHALL require the "audit:read" permission for access to the UDP port status endpoint.

### Requirement 3: TURN/STUN Service Availability Check

**User Story:** As an administrator, I want to verify that the TURN/STUN service is reachable, so that I can confirm NAT traversal is operational for clients behind restrictive firewalls.

#### Acceptance Criteria

1. WHEN an authenticated administrator requests TURN/STUN availability, THE UDP_Monitor_API SHALL perform a TCP connectivity check to the TURN_STUN_Service on port 7881.
2. THE UDP_Monitor_API SHALL report the service reachability status (reachable or unreachable) and the connection latency in milliseconds.
3. IF the TURN_STUN_Service connection attempt times out after 3 seconds, THEN THE UDP_Monitor_API SHALL report the service as unreachable with a timeout indicator.
4. THE UDP_Monitor_API SHALL require the "audit:read" permission for access to the TURN/STUN check endpoint.

### Requirement 4: UDP/WebRTC Monitor Frontend Page

**User Story:** As an administrator, I want a dedicated UDP/WebRTC monitoring sub-page accessible from the existing Monitor page, so that I can view all UDP and WebRTC metrics in one organized view.

#### Acceptance Criteria

1. THE UDP_Monitor_Page SHALL be accessible via a navigation link from the existing Monitor page.
2. THE UDP_Monitor_Page SHALL be routed under `/admin/monitor/udp` and require the "audit:read" capability for access.
3. THE UDP_Monitor_Page SHALL display WebRTC participant track statistics grouped by room and participant, showing packet loss, RTT, jitter, and bitrate for each track.
4. THE UDP_Monitor_Page SHALL display ICE candidate type and connection state for each participant.
5. THE UDP_Monitor_Page SHALL display UDP port usage status for the port range 50000–50020, indicating bound and free ports with packet counters.
6. THE UDP_Monitor_Page SHALL display UDP socket buffer queue sizes for each bound port.
7. THE UDP_Monitor_Page SHALL display TURN/STUN service reachability status and latency.
8. THE UDP_Monitor_Page SHALL provide a manual refresh button that fetches all monitoring data on demand.
9. THE UDP_Monitor_Page SHALL auto-refresh monitoring data every 10 seconds.
10. WHILE monitoring data is loading, THE UDP_Monitor_Page SHALL display a loading indicator.
11. IF any API request fails, THEN THE UDP_Monitor_Page SHALL display the error message returned by the API within the relevant section without blocking other sections from rendering.

### Requirement 5: Real-Time Snapshot Data Model

**User Story:** As an administrator, I want all monitoring data to reflect the current system state at the time of request, so that I can make decisions based on live conditions.

#### Acceptance Criteria

1. THE UDP_Monitor_API SHALL return fresh data from LiveKit_RoomService and System_UDP_Inspector on each request without caching or historical storage.
2. THE UDP_Monitor_API SHALL include a UTC timestamp in each response indicating when the snapshot was captured.
3. THE UDP_Monitor_API SHALL complete each monitoring request within 5 seconds under normal operating conditions.
