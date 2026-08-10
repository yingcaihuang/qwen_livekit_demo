# Design Document: Realtime Translate & Transcribe

## Architecture Overview

This feature extends the existing AI Testing Platform by adding two new instance types and their corresponding session workflows. The architecture mirrors the existing voice session pattern:

```
┌─────────────┐    HTTP/WS    ┌──────────────┐   subprocess   ┌─────────────────────┐
│  Frontend   │ ◄──────────► │   Backend    │ ────────────► │  Worker Process     │
│ (React)     │               │  (FastAPI)   │               │ (livekit-agents)    │
└─────────────┘               └──────────────┘               └─────────────────────┘
       │                             │                               │
       │         LiveKit Room (audio/events)                         │
       └────────────────────────────────────────────────────────────┘
```

Key architectural decisions:
- **Separate worker scripts** per model type (translate_worker.py, transcribe_worker.py) rather than a single parametrized worker, for clarity and independent evolution.
- **Separate API endpoints** per session type (`/api/translate-sessions`, `/api/transcribe-sessions`) for clear type safety at the API boundary.
- **Shared Process Manager** with a configurable `worker_script` parameter.
- **Language settings persisted** in the sessions table as nullable columns.

## Components

### Backend Components

#### 1. Instance Type Extension

**File:** `backend/app/models/instance.py`

```python
# Extend the InstanceType Literal
InstanceType = Literal["voice", "chat", "image", "translate", "transcribe"]
```

No other changes to instance models — they already store endpoint, api_key, deployment, and type.

#### 2. Translate Worker (`backend/app/translate_worker.py`)

Structure mirrors `agent_worker.py` with key differences:

```python
"""Translate Worker: spawned per Translate Session.

Connects to LiveKit room, uses Azure OpenAI Realtime API in translation mode.
Outputs translated audio to the room and emits text transcript events.

Additional env vars:
    TARGET_LANGUAGE - ISO 639-1 language code for translation target (e.g., "en", "zh")
"""

class TranslateAssistant(Agent):
    """Translation agent — relays translated audio and text."""
    def __init__(self, target_language: str) -> None:
        super().__init__(
            instructions=f"You are a real-time translator. Translate all spoken input into {target_language}."
        )

async def entrypoint(ctx: JobContext) -> None:
    target_language = os.environ.get("TARGET_LANGUAGE", "en")
    # ... same pattern as agent_worker.py:
    # 1. Read Azure creds from env
    # 2. Connect to LiveKit room
    # 3. Create RealtimeModel.with_azure() using translate deployment
    # 4. Configure session with target_language
    # 5. Start AgentSession (publishes audio + emits events)
    # 6. Track and report token usage
```

#### 3. Transcribe Worker (`backend/app/transcribe_worker.py`)

```python
"""Transcribe Worker: spawned per Transcribe Session.

Connects to LiveKit room, uses Azure OpenAI Realtime API in transcription mode.
Emits real-time text transcript events only (no audio output).

Additional env vars:
    SOURCE_LANGUAGE - ISO 639-1 language code hint (e.g., "en", "zh") or empty for auto-detect
"""

class TranscribeAssistant(Agent):
    """Transcription agent — outputs text only, no audio."""
    def __init__(self, source_language: str) -> None:
        lang_hint = f" The spoken language is {source_language}." if source_language else ""
        super().__init__(
            instructions=f"You are a real-time transcriber. Output text transcription of all spoken input.{lang_hint}"
        )

async def entrypoint(ctx: JobContext) -> None:
    source_language = os.environ.get("SOURCE_LANGUAGE", "")
    # ... same structure as agent_worker.py but:
    # - No audio output (agent session configured for text-only response)
    # - Emits transcript text events via conversation_item_added handler
```

#### 4. Process Manager Extension (`backend/app/services/process_manager.py`)

```python
async def spawn_agent(
    self,
    session_id: str,
    instance_config: dict,
    room_name: str,
    voice: str = "alloy",
    worker_script: str | None = None,  # NEW: path to worker script
    extra_env: dict[str, str] | None = None,  # NEW: additional env vars
) -> None:
    # Resolve worker script
    if worker_script:
        agent_script = str(Path(__file__).resolve().parent.parent / worker_script)
    else:
        agent_script = str(_AGENT_WORKER_PATH)

    # Merge extra_env into subprocess environment
    env = os.environ.copy()
    env.update({...existing vars...})
    if extra_env:
        env.update(extra_env)
```

#### 5. Session Models Extension (`backend/app/models/session.py`)

```python
class TranslateSessionCreate(BaseModel):
    """Request model for creating a translate session."""
    instance_id: str
    target_language: str  # ISO 639-1 code

class TranscribeSessionCreate(BaseModel):
    """Request model for creating a transcribe session."""
    instance_id: str
    source_language: str = ""  # Empty string = auto-detect
```

#### 6. Session Service Extension (`backend/app/services/session_service.py`)

New methods:

```python
async def create_translate_session(
    self, db, instance_id: str, target_language: str, *, user=None
) -> SessionResponse:
    # 1. Verify instance exists AND type == "translate"
    # 2. Create session record with target_language persisted
    # 3. Spawn translate_worker.py with TARGET_LANGUAGE env var
    # 4. Return LiveKit connection info

async def create_transcribe_session(
    self, db, instance_id: str, source_language: str, *, user=None
) -> SessionResponse:
    # 1. Verify instance exists AND type == "transcribe"
    # 2. Create session record with source_language persisted
    # 3. Spawn transcribe_worker.py with SOURCE_LANGUAGE env var
    # 4. Return LiveKit connection info
```

#### 7. API Routes (`backend/app/api/translate_sessions.py`, `backend/app/api/transcribe_sessions.py`)

```python
# translate_sessions.py
router = APIRouter(prefix="/api/translate-sessions", tags=["translate-sessions"])

@router.post("", status_code=201, response_model=SessionResponse)
async def create_translate_session(data: TranslateSessionCreate, ...):
    return await _session_service.create_translate_session(db, data.instance_id, data.target_language, user=user)

# transcribe_sessions.py
router = APIRouter(prefix="/api/transcribe-sessions", tags=["transcribe-sessions"])

@router.post("", status_code=201, response_model=SessionResponse)
async def create_transcribe_session(data: TranscribeSessionCreate, ...):
    return await _session_service.create_transcribe_session(db, data.instance_id, data.source_language, user=user)
```

#### 8. Database Schema Extension

```sql
-- Add nullable language columns to sessions table
ALTER TABLE sessions ADD COLUMN target_language TEXT;
ALTER TABLE sessions ADD COLUMN source_language TEXT;
```

Applied via migration or schema update in `schema.sql`.

### Frontend Components

#### 9. TranslatePage (`frontend/src/pages/TranslatePage.tsx`)

Follows the same pattern as `VoiceSessionPage.tsx`:
- Instance selector (filtered to type "translate" via query param or fetching filtered list)
- Target language dropdown (common ISO 639-1 codes with display names)
- Start/Stop buttons
- LiveKit room connection (with audio playback for translated output)
- Real-time transcript display (via WebSocket debug console or dedicated transcript panel)
- Token usage display

#### 10. TranscribePage (`frontend/src/pages/TranscribePage.tsx`)

Similar to TranslatePage but:
- Source language dropdown with "Auto-detect" default
- No audio playback (text-only output)
- Scrolling text transcript as primary display

#### 11. Sidebar & Routing Updates

```typescript
// Sidebar navItems addition
{ label: '实时翻译', path: '/translate/new', icon: Languages, capability: 'translate:use' },
{ label: '实时转录', path: '/transcribe/new', icon: FileText, capability: 'transcribe:use' },

// App.tsx routes
<Route path="/translate/new" element={<ProtectedRoute capability="translate:use"><AppShell><TranslatePage /></AppShell></ProtectedRoute>} />
<Route path="/transcribe/new" element={<ProtectedRoute capability="transcribe:use"><AppShell><TranscribePage /></AppShell></ProtectedRoute>} />
```

#### 12. Instance Form Extension

Update `InstanceFormPage.tsx` type selector to include "translate" and "transcribe" options.

## Data Models

### Sessions Table (Extended)

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | Session identifier |
| instance_id | TEXT FK | References instances(id) |
| room_name | TEXT | LiveKit room name |
| status | TEXT | connecting/active/cancelled/error |
| start_time | TEXT | ISO timestamp |
| end_time | TEXT | ISO timestamp (nullable) |
| input_tokens | INTEGER | Accumulated input tokens |
| output_tokens | INTEGER | Accumulated output tokens |
| error_message | TEXT | Error details (nullable) |
| created_by | TEXT | User ID for multi-tenant |
| **target_language** | **TEXT** | **Target language for translate sessions (nullable)** |
| **source_language** | **TEXT** | **Source language hint for transcribe sessions (nullable)** |

### Language Options

```typescript
const TARGET_LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'zh', label: '中文 (Chinese)' },
  { value: 'ja', label: '日本語 (Japanese)' },
  { value: 'ko', label: '한국어 (Korean)' },
  { value: 'es', label: 'Español (Spanish)' },
  { value: 'fr', label: 'Français (French)' },
  { value: 'de', label: 'Deutsch (German)' },
  { value: 'pt', label: 'Português (Portuguese)' },
  { value: 'ru', label: 'Русский (Russian)' },
  { value: 'ar', label: 'العربية (Arabic)' },
  { value: 'hi', label: 'हिन्दी (Hindi)' },
  { value: 'it', label: 'Italiano (Italian)' },
]

const SOURCE_LANGUAGES = [
  { value: '', label: 'Auto-detect' },
  ...TARGET_LANGUAGES,
]
```

## Interfaces

### API Endpoints

| Method | Path | Request Body | Response |
|--------|------|-------------|----------|
| POST | /api/translate-sessions | `{instance_id, target_language}` | SessionResponse |
| POST | /api/transcribe-sessions | `{instance_id, source_language}` | SessionResponse |

Both return the same `SessionResponse` model as the existing sessions endpoint:
```json
{
  "session_id": "string",
  "room_name": "string",
  "livekit_token": "string",
  "livekit_url": "string"
}
```

### Worker Environment Variables

| Variable | Worker | Description |
|----------|--------|-------------|
| TARGET_LANGUAGE | translate_worker.py | ISO 639-1 target language code |
| SOURCE_LANGUAGE | transcribe_worker.py | ISO 639-1 source language hint (empty = auto) |
| AZURE_ENDPOINT | all workers | Azure OpenAI endpoint URL |
| AZURE_API_KEY | all workers | Azure OpenAI API key |
| AZURE_DEPLOYMENT | all workers | Deployment name |
| LIVEKIT_URL | all workers | LiveKit WebSocket URL |
| LIVEKIT_API_KEY | all workers | LiveKit API key |
| LIVEKIT_API_SECRET | all workers | LiveKit API secret |
| ROOM_NAME | all workers | LiveKit room to join |
| SESSION_ID | all workers | Session ID for usage reporting |
| REPORT_URL | all workers | Internal usage reporting URL |

## Error Handling

| Scenario | Response |
|----------|----------|
| Instance not found | HTTP 404 "Instance not found" |
| Instance type mismatch (e.g., voice instance for translate endpoint) | HTTP 400 "Instance type must be 'translate'" |
| Missing target_language for translate | HTTP 422 (Pydantic validation) |
| Worker spawn failure | Session created with status "connecting"; error logged; session can be stopped manually |
| Worker crash during session | Usage reported via safety-net report_usage(); session status remains until manually stopped |
| Invalid language code | Accepted as-is (Azure API handles validation); no client-side hard validation |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Instance type validation accepts exactly the defined types

*For any* string value submitted as an instance type, the Platform SHALL accept it if and only if it is one of "voice", "chat", "image", "translate", or "transcribe".

**Validates: Requirements 1.1, 1.4**

### Property 2: Session creation persists language settings correctly

*For any* translate session created with a target_language value, or any transcribe session created with a source_language value, the corresponding column in the sessions database record SHALL contain that exact value after creation.

**Validates: Requirements 2.1, 3.1, 9.1, 9.2**

### Property 3: Type-specific endpoints reject mismatched instance types

*For any* instance whose type is not "translate", a POST to /api/translate-sessions referencing that instance SHALL return HTTP 400. Similarly, for any instance whose type is not "transcribe", a POST to /api/transcribe-sessions referencing that instance SHALL return HTTP 400.

**Validates: Requirements 4.3, 4.4**

### Property 4: Process Manager dispatches the correct worker script for each session type

*For any* session spawned via the Process Manager, the executed worker script SHALL correspond to the instance type: "translate" maps to translate_worker.py, "transcribe" maps to transcribe_worker.py, and "voice" (or unspecified) maps to agent_worker.py.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4**
