# Requirements Document

## Introduction

This feature extends the AI Testing Platform to support two new Azure OpenAI Realtime model types: GPT Realtime Translate (real-time audio translation) and GPT Realtime Transcribe (real-time audio transcription). Both use the same LiveKit + livekit-agents + openai realtime plugin architecture as the existing voice model but with different session configurations and output modes.

## Glossary

- **Platform**: The AI Testing Platform (azure-voice-admin) comprising a FastAPI backend and React frontend.
- **Instance**: A configured Azure OpenAI deployment endpoint stored in the database with type, credentials, and deployment name.
- **Session**: A single real-time interaction between a user and an Azure model, mediated through a LiveKit room and an Agent Worker subprocess.
- **Agent_Worker**: A Python subprocess spawned by the Process Manager that connects to a LiveKit room and interacts with an Azure OpenAI Realtime model.
- **Translate_Worker**: An Agent Worker specialized for real-time audio translation, outputting translated audio and text.
- **Transcribe_Worker**: An Agent Worker specialized for real-time audio transcription, outputting text only.
- **Process_Manager**: The singleton service responsible for spawning, monitoring, and terminating Agent Worker subprocesses.
- **Session_Service**: The business logic layer managing session lifecycle including creation, stopping, and usage reporting.
- **LiveKit_Room**: A real-time communication room provided by the LiveKit server for audio/video streaming between participants.
- **Target_Language**: The language into which audio input is translated (used by Translate sessions).
- **Source_Language**: A language hint indicating the spoken input language (used by Transcribe sessions for improved accuracy).

## Requirements

### Requirement 1

**User Story:** As a platform administrator, I want to create instances of type "translate" and "transcribe", so that I can configure Azure OpenAI Realtime Translate and Transcribe deployments for testing.

#### Acceptance Criteria

1. THE Platform SHALL accept "translate" and "transcribe" as valid values for the instance type field during instance creation.
2. WHEN a user creates an instance with type "translate", THE Platform SHALL store the instance with type "translate" and display it in the instance list with a distinguishable type label.
3. WHEN a user creates an instance with type "transcribe", THE Platform SHALL store the instance with type "transcribe" and display it in the instance list with a distinguishable type label.
4. THE Platform SHALL continue to accept "voice", "chat", and "image" as valid instance types without modification to existing behavior.

### Requirement 2

**User Story:** As a tester, I want to start a real-time translation session, so that I can test Azure OpenAI Realtime Translate by speaking and hearing the translated audio output.

#### Acceptance Criteria

1. WHEN a user starts a translate session with a valid translate instance and target language, THE Platform SHALL create a session record with status "connecting", persist the target_language value, and return LiveKit connection info.
2. WHEN a translate session is created, THE Platform SHALL spawn a Translate_Worker subprocess configured with the instance Azure credentials, room name, and target language.
3. WHILE a translate session is active, THE Translate_Worker SHALL publish translated audio back to the LiveKit_Room so the user hears the translation in real-time.
4. WHILE a translate session is active, THE Translate_Worker SHALL emit text transcript events containing the translated text for display in the frontend.
5. WHEN the Translate_Worker accumulates token usage, THE Translate_Worker SHALL report input_tokens and output_tokens to the Platform via the internal usage endpoint.
6. WHEN a user stops a translate session, THE Platform SHALL terminate the Translate_Worker subprocess and update the session status to "cancelled" with an end_time.

### Requirement 3

**User Story:** As a tester, I want to start a real-time transcription session, so that I can test Azure OpenAI Realtime Transcribe by speaking and seeing the live text transcript.

#### Acceptance Criteria

1. WHEN a user starts a transcribe session with a valid transcribe instance and optional source language, THE Platform SHALL create a session record with status "connecting", persist the source_language value, and return LiveKit connection info.
2. WHEN a transcribe session is created, THE Platform SHALL spawn a Transcribe_Worker subprocess configured with the instance Azure credentials, room name, and source language hint.
3. WHILE a transcribe session is active, THE Transcribe_Worker SHALL emit real-time text transcript events containing the recognized speech for display in the frontend.
4. THE Transcribe_Worker SHALL NOT publish audio output to the LiveKit_Room (transcription is text-only).
5. WHEN the Transcribe_Worker accumulates token usage, THE Transcribe_Worker SHALL report input_tokens and output_tokens to the Platform via the internal usage endpoint.
6. WHEN a user stops a transcribe session, THE Platform SHALL terminate the Transcribe_Worker subprocess and update the session status to "cancelled" with an end_time.

### Requirement 4

**User Story:** As a developer, I want a dedicated API endpoint for translate sessions and another for transcribe sessions, so that the session creation logic is clearly separated by type.

#### Acceptance Criteria

1. THE Platform SHALL expose a POST /api/translate-sessions endpoint that accepts instance_id and target_language fields.
2. THE Platform SHALL expose a POST /api/transcribe-sessions endpoint that accepts instance_id and source_language fields.
3. WHEN a request to POST /api/translate-sessions references an instance whose type is not "translate", THE Platform SHALL return HTTP 400 with a descriptive error message.
4. WHEN a request to POST /api/transcribe-sessions references an instance whose type is not "transcribe", THE Platform SHALL return HTTP 400 with a descriptive error message.
5. THE existing POST /api/sessions endpoint SHALL remain unchanged and continue to serve voice sessions only.

### Requirement 5

**User Story:** As a developer, I want the Process Manager to support spawning different worker scripts based on instance type, so that translate and transcribe sessions use the correct worker logic.

#### Acceptance Criteria

1. WHEN the Process_Manager spawns an agent for a translate session, THE Process_Manager SHALL execute the translate_worker.py script with the TARGET_LANGUAGE environment variable set.
2. WHEN the Process_Manager spawns an agent for a transcribe session, THE Process_Manager SHALL execute the transcribe_worker.py script with the SOURCE_LANGUAGE environment variable set.
3. THE Process_Manager SHALL accept a worker_script parameter specifying which Python script to execute, replacing the previously hardcoded agent_worker.py path.
4. THE Process_Manager SHALL continue to spawn agent_worker.py for voice sessions when no explicit worker_script is provided.

### Requirement 6

**User Story:** As a tester, I want a Translate page in the frontend, so that I can select a translate instance, choose a target language, and interact with the real-time translation.

#### Acceptance Criteria

1. THE Platform SHALL display a TranslatePage accessible at route /translate/new with an instance selector filtered to instances of type "translate".
2. THE TranslatePage SHALL provide a target language dropdown with common language options (en, zh, ja, ko, es, fr, de, pt, ru, ar, hi, it).
3. WHEN the user clicks Start, THE TranslatePage SHALL call POST /api/translate-sessions with the selected instance_id and target_language, then connect to the LiveKit room.
4. WHILE a translate session is active, THE TranslatePage SHALL play the translated audio track from the LiveKit room and display the translated text transcript in real-time.
5. WHEN the user clicks Stop, THE TranslatePage SHALL disconnect from the LiveKit room and call the stop endpoint to terminate the session.
6. THE TranslatePage SHALL display token usage information during the active session.

### Requirement 7

**User Story:** As a tester, I want a Transcribe page in the frontend, so that I can select a transcribe instance, optionally set a source language, and view live transcription text.

#### Acceptance Criteria

1. THE Platform SHALL display a TranscribePage accessible at route /transcribe/new with an instance selector filtered to instances of type "transcribe".
2. THE TranscribePage SHALL provide a source language dropdown with common language options including an "auto-detect" option as default.
3. WHEN the user clicks Start, THE TranscribePage SHALL call POST /api/transcribe-sessions with the selected instance_id and source_language, then connect to the LiveKit room.
4. WHILE a transcribe session is active, THE TranscribePage SHALL display a scrolling real-time text transcript of the recognized speech.
5. WHEN the user clicks Stop, THE TranscribePage SHALL disconnect from the LiveKit room and call the stop endpoint to terminate the session.
6. THE TranscribePage SHALL display token usage information during the active session.

### Requirement 8

**User Story:** As a user, I want navigation items for translate and transcribe in the sidebar, so that I can easily access the new features.

#### Acceptance Criteria

1. THE Sidebar SHALL include a "实时翻译" navigation item linked to /translate/new with an appropriate icon.
2. THE Sidebar SHALL include a "实时转录" navigation item linked to /transcribe/new with an appropriate icon.
3. THE Platform SHALL register routes /translate/new and /transcribe/new in App.tsx with appropriate capability guards.
4. THE instance creation form SHALL allow selecting "translate" and "transcribe" as instance type options.

### Requirement 9

**User Story:** As a platform operator, I want the session history to show language settings for translate and transcribe sessions, so that I can review past session configurations.

#### Acceptance Criteria

1. THE sessions database table SHALL include a target_language column (nullable TEXT) for storing translate session language settings.
2. THE sessions database table SHALL include a source_language column (nullable TEXT) for storing transcribe session language hints.
3. WHEN displaying session history, THE Platform SHALL show the target_language or source_language value for translate and transcribe sessions respectively.

### Requirement 10

**User Story:** As a platform operator, I want existing voice, chat, and image functionality to remain unaffected by the new features, so that there are no regressions.

#### Acceptance Criteria

1. THE Platform SHALL continue to create and manage voice sessions via POST /api/sessions without any change in behavior or API contract.
2. THE Platform SHALL continue to create and manage chat sessions via the existing chat API without modification.
3. THE Platform SHALL continue to create and manage image generations via the existing images API without modification.
4. THE existing agent_worker.py SHALL remain unchanged and continue to serve voice sessions.
