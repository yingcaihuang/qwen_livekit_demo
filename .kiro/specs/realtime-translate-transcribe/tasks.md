# Implementation Plan: Realtime Translate & Transcribe

## Overview

Add GPT Realtime Translate and GPT Realtime Transcribe model support to the AI Testing Platform. This involves extending instance types, creating two new worker scripts, adding dedicated API endpoints, updating the Process Manager, and building two new frontend pages with navigation updates.

## Tasks

- [ ] 1. Extend instance type and database schema
  - [ ] 1.1 Update InstanceType Literal and instance form
    - Add "translate" and "transcribe" to `InstanceType` in `backend/app/models/instance.py`
    - Update `frontend/src/pages/InstanceFormPage.tsx` type selector to include "translate" and "transcribe" options
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 8.4_

  - [ ] 1.2 Add language columns to sessions table
    - Add `target_language TEXT` and `source_language TEXT` nullable columns to sessions table in `backend/app/schema.sql`
    - Add migration logic in `backend/app/database.py` to ALTER TABLE if columns don't exist
    - _Requirements: 9.1, 9.2_

  - [ ]* 1.3 Write property test for instance type validation
    - **Property 1: Instance type validation accepts exactly the defined types**
    - **Validates: Requirements 1.1, 1.4**

- [ ] 2. Implement Translate Worker
  - [ ] 2.1 Create translate_worker.py
    - Create `backend/app/translate_worker.py` following the same structure as `agent_worker.py`
    - Read TARGET_LANGUAGE from environment variables
    - Configure TranslateAssistant agent with translation instructions
    - Use `openai.realtime.RealtimeModel.with_azure()` with the translate deployment
    - Publish translated audio to the LiveKit room
    - Emit text transcript events via conversation_item_added handler
    - Report token usage via the internal usage endpoint
    - _Requirements: 2.2, 2.3, 2.4, 2.5_

- [ ] 3. Implement Transcribe Worker
  - [ ] 3.1 Create transcribe_worker.py
    - Create `backend/app/transcribe_worker.py` following the same structure as `agent_worker.py`
    - Read SOURCE_LANGUAGE from environment variables
    - Configure TranscribeAssistant agent with transcription instructions (text-only, no audio output)
    - Use `openai.realtime.RealtimeModel.with_azure()` with the transcribe deployment
    - Emit real-time text transcript events via conversation_item_added handler
    - Do NOT publish audio output to the room
    - Report token usage via the internal usage endpoint
    - _Requirements: 3.2, 3.3, 3.4, 3.5_

- [ ] 4. Extend Process Manager and Session Service
  - [ ] 4.1 Update Process Manager to accept worker_script parameter
    - Add `worker_script: str | None = None` and `extra_env: dict[str, str] | None = None` parameters to `spawn_agent()`
    - Resolve worker_script path relative to backend/app/ directory
    - Default to existing `_AGENT_WORKER_PATH` when worker_script is None
    - Merge extra_env into subprocess environment
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 4.2 Write property test for Process Manager worker dispatch
    - **Property 4: Process Manager dispatches the correct worker script for each session type**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

  - [ ] 4.3 Add session models for translate and transcribe
    - Add `TranslateSessionCreate` model (instance_id, target_language) to `backend/app/models/session.py`
    - Add `TranscribeSessionCreate` model (instance_id, source_language with default "") to `backend/app/models/session.py`
    - _Requirements: 4.1, 4.2_

  - [ ] 4.4 Implement create_translate_session in Session Service
    - Add `create_translate_session()` method to SessionService
    - Verify instance exists and type == "translate" (HTTP 400 if mismatch)
    - Create session record with target_language column populated
    - Spawn translate_worker.py via Process Manager with TARGET_LANGUAGE env var
    - Return LiveKit connection info
    - _Requirements: 2.1, 2.2, 4.3_

  - [ ] 4.5 Implement create_transcribe_session in Session Service
    - Add `create_transcribe_session()` method to SessionService
    - Verify instance exists and type == "transcribe" (HTTP 400 if mismatch)
    - Create session record with source_language column populated
    - Spawn transcribe_worker.py via Process Manager with SOURCE_LANGUAGE env var
    - Return LiveKit connection info
    - _Requirements: 3.1, 3.2, 4.4_

  - [ ]* 4.6 Write property tests for type-specific endpoints and session creation
    - **Property 3: Type-specific endpoints reject mismatched instance types**
    - **Property 2: Session creation persists language settings correctly**
    - **Validates: Requirements 2.1, 3.1, 4.3, 4.4, 9.1, 9.2**

- [ ] 5. Create API routes for translate and transcribe sessions
  - [ ] 5.1 Create translate_sessions.py API router
    - Create `backend/app/api/translate_sessions.py`
    - POST /api/translate-sessions endpoint accepting TranslateSessionCreate body
    - Wire auth with `require_permission("translate:use")`
    - Register router in `backend/app/main.py`
    - _Requirements: 4.1, 4.3_

  - [ ] 5.2 Create transcribe_sessions.py API router
    - Create `backend/app/api/transcribe_sessions.py`
    - POST /api/transcribe-sessions endpoint accepting TranscribeSessionCreate body
    - Wire auth with `require_permission("transcribe:use")`
    - Register router in `backend/app/main.py`
    - _Requirements: 4.2, 4.4_

  - [ ] 5.3 Update session history display to include language columns
    - Update `SessionDetail` model to include optional target_language and source_language fields
    - Update list_sessions and get_session queries to SELECT the new columns
    - _Requirements: 9.3_

- [ ] 6. Checkpoint - Backend complete
  - Ensure all backend tests pass, ask the user if questions arise.

- [ ] 7. Implement TranslatePage frontend
  - [ ] 7.1 Create TranslatePage component
    - Create `frontend/src/pages/TranslatePage.tsx`
    - Instance selector filtered to type "translate" (fetch /api/instances?type=translate or filter client-side)
    - Target language dropdown with common languages (en, zh, ja, ko, es, fr, de, pt, ru, ar, hi, it)
    - Start button: calls POST /api/translate-sessions with selected instance_id and target_language
    - Connects to LiveKit room on session creation
    - Plays translated audio track from LiveKit room
    - Displays real-time translated text transcript (via DebugConsole or custom transcript panel)
    - Stop button: disconnects LiveKit and calls POST /api/sessions/{id}/stop
    - Token usage display
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [ ] 8. Implement TranscribePage frontend
  - [ ] 8.1 Create TranscribePage component
    - Create `frontend/src/pages/TranscribePage.tsx`
    - Instance selector filtered to type "transcribe"
    - Source language dropdown with "Auto-detect" default plus common languages
    - Start button: calls POST /api/transcribe-sessions with selected instance_id and source_language
    - Connects to LiveKit room on session creation
    - No audio playback (text-only)
    - Scrolling real-time text transcript display
    - Stop button: disconnects LiveKit and calls POST /api/sessions/{id}/stop
    - Token usage display
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [ ] 9. Update navigation and routing
  - [ ] 9.1 Update Sidebar and App.tsx
    - Add "实时翻译" nav item with Languages icon to Sidebar (capability: 'translate:use')
    - Add "实时转录" nav item with FileText icon to Sidebar (capability: 'transcribe:use')
    - Add route /translate/new → TranslatePage in App.tsx with ProtectedRoute capability="translate:use"
    - Add route /transcribe/new → TranscribePage in App.tsx with ProtectedRoute capability="transcribe:use"
    - _Requirements: 8.1, 8.2, 8.3_

- [ ] 10. Final checkpoint
  - Ensure all tests pass, verify existing voice/chat/image flows are unaffected, ask the user if questions arise.
  - _Requirements: 10.1, 10.2, 10.3, 10.4_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The translate and transcribe workers share 90% of their structure with agent_worker.py — copy and modify
- Both new API routers follow the same pattern as sessions.py
- Frontend pages follow the same pattern as VoiceSessionPage.tsx with language selectors instead of voice selectors

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1", "3.1", "4.1"] },
    { "id": 2, "tasks": ["4.2", "4.3"] },
    { "id": 3, "tasks": ["4.4", "4.5"] },
    { "id": 4, "tasks": ["4.6", "5.1", "5.2"] },
    { "id": 5, "tasks": ["5.3"] },
    { "id": 6, "tasks": ["7.1", "8.1"] },
    { "id": 7, "tasks": ["9.1"] }
  ]
}
```
