# Design Document: Multi-Image Editing

## Architecture Overview

This feature extends the existing image generation system with three new capabilities: multi-reference image support, mask-based editing, and an `input_fidelity` parameter. The architecture preserves the current async queue/job model where the API handler enqueues a job and a background worker processes it.

**Key design decisions:**
- The API endpoint signature changes minimally (adds `files`, `mask`, `input_fidelity` form fields) while keeping the legacy `file` field for backward compatibility.
- Multiple reference images are persisted to disk with indexed filenames (`_reference_0.png`, `_reference_1.jpg`) so the background worker can reconstruct the multipart request to Azure.
- The mask is persisted as `_mask.png` alongside references.
- Frontend validation mirrors backend validation to provide immediate feedback; the backend remains authoritative.

## Component Design

### 1. Backend API Layer (`app/api/images.py`)

#### Modified Endpoint: `POST /api/images/generations`

```python
@router.post("/generations", status_code=HTTP_202_ACCEPTED)
async def create_generation(
    instance_id: str = Form(...),
    prompt: str = Form(...),
    size: str = Form("1024x1024"),
    quality: str = Form("high"),
    output_format: str = Form("png"),
    compression: int = Form(100),
    n: int = Form(1),
    input_fidelity: str | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    mask: UploadFile | None = File(default=None),
    # Legacy single-file field for backward compatibility
    file: UploadFile | None = File(default=None),
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(require_permission("image:use")),
) -> JSONResponse:
    ...
```

**Validation logic (before enqueue):**

```python
# Merge legacy `file` into `files` list for unified handling
all_files = list(files)
if file is not None and not files:
    all_files = [file]

# Validate count
if len(all_files) > 10:
    raise HTTPException(422, detail="参考图最多 10 张")

# Validate each file: format and size
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/jpg"}
MAX_SIZE = 50 * 1024 * 1024  # 50MB

for f in all_files:
    if not _is_allowed_image(f):
        raise HTTPException(422, detail="仅支持 PNG 和 JPG 格式")
    content = await f.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(413, detail="图片大小不能超过 50MB")
    await f.seek(0)

# Validate mask
if mask is not None:
    if not _is_png(mask):
        raise HTTPException(422, detail="遮罩图必须是 PNG 格式")
    mask_content = await mask.read()
    if len(mask_content) > MAX_SIZE:
        raise HTTPException(413, detail="遮罩图大小不能超过 50MB")
    await mask.seek(0)
    if not all_files:
        raise HTTPException(422, detail="使用遮罩需要至少上传一张参考图")
```

**Helper: `_is_allowed_image`** validates via magic bytes (PNG signature or JPEG SOI marker), same approach as existing `_detect_image_type`.

### 2. Backend Service Layer (`app/services/image_service.py`)

#### Modified: `enqueue_generation`

Changes:
- Accept `reference_images: list[UploadFile | bytes]` (replaces single `reference_image`).
- Accept `mask: UploadFile | bytes | None`.
- Accept `input_fidelity: str | None`.
- Persist multiple references as `_reference_0.<ext>`, `_reference_1.<ext>`, etc.
- Persist mask as `_mask.png`.
- Store `input_fidelity` in the `params` JSON column.
- Store reference count in a new column or as part of params for the worker to know how many to read.

```python
async def enqueue_generation(
    self,
    db: aiosqlite.Connection,
    request: ImageGenerationRequest,
    reference_images: list[UploadFile | bytes] | None = None,
    mask: UploadFile | bytes | None = None,
    *,
    input_fidelity: str | None = None,
    created_by: str | None = None,
) -> dict:
    ...
```

#### Modified: `_call_edits`

Changes to support multiple images:

```python
async def _call_edits(
    self,
    endpoint: str,
    api_key: str,
    deployment: str,
    prompt: str,
    params: ImageParams,
    reference_images: list[tuple[bytes, str, str]],  # [(data, content_type, filename), ...]
    mask_bytes: bytes | None = None,
    input_fidelity: str | None = None,
) -> tuple[dict, int, int]:
    url = self._azure_edits_url(endpoint)
    form = aiohttp.FormData()
    form.add_field("model", deployment)
    form.add_field("prompt", prompt)
    form.add_field("size", params.size)
    form.add_field("quality", params.quality)
    form.add_field("output_format", params.output_format)
    form.add_field("output_compression", str(params.compression))
    form.add_field("n", str(params.n))

    # Multiple reference images as image[] fields
    for data, content_type, filename in reference_images:
        form.add_field("image[]", data, filename=filename, content_type=content_type)

    # Optional mask
    if mask_bytes is not None:
        form.add_field("mask", mask_bytes, filename="mask.png", content_type="image/png")

    # Optional input_fidelity
    if input_fidelity is not None:
        form.add_field("input_fidelity", input_fidelity)

    headers = {"api-key": api_key}
    return await self._post(url, headers=headers, data=form)
```

#### Modified: `process_job`

Changes:
- Read all `_reference_*` files from the generation directory (sorted by index).
- Read `_mask.png` if present.
- Extract `input_fidelity` from the stored params JSON.
- Pass all to `_call_edits`.

```python
# In process_job, after loading the row:
reference_files = self._read_all_saved_references(gen_dir)
mask_bytes = self._read_saved_mask(gen_dir)
input_fidelity = params_dict.get("input_fidelity")

if reference_files:
    payload, ttfb_ms, total_ms = await self._call_edits(
        endpoint, api_key, deployment, prompt, params,
        reference_images=reference_files,
        mask_bytes=mask_bytes,
        input_fidelity=input_fidelity,
    )
else:
    payload, ttfb_ms, total_ms = await self._call_generations(
        endpoint, api_key, deployment, prompt, params
    )
```

#### New Helper: `_read_all_saved_references`

```python
@staticmethod
def _read_all_saved_references(gen_dir: Path) -> list[tuple[bytes, str, str]]:
    """Read all _reference_N.* files, sorted by index."""
    if not gen_dir.exists():
        return []
    matches = sorted(gen_dir.glob("_reference_*"))
    results = []
    for path in matches:
        if path.name.startswith("_reference_") and path.is_file():
            data = path.read_bytes()
            ext = path.suffix.lstrip(".")
            content_type = ImageService._MEDIA_TYPES.get(ext, "image/png")
            results.append((data, content_type, path.name))
    return results
```

#### New Helper: `_read_saved_mask`

```python
@staticmethod
def _read_saved_mask(gen_dir: Path) -> bytes | None:
    """Read the saved _mask.png file, or None."""
    mask_path = gen_dir / "_mask.png"
    if mask_path.is_file():
        return mask_path.read_bytes()
    return None
```

#### Modified: Error handling in `_post`

```python
# Enhanced error classification in process_job exception handler:
if resp.status == 429:
    raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试")

# After parsing JSON error response:
error_body = json.loads(text)
error_code = error_body.get("error", {}).get("code", "")
if error_code == "content_policy_violation":
    raise HTTPException(status_code=400, detail="内容被安全系统拦截，请修改提示词")
```

### 3. Data Model Changes

#### `ImageParams` (Pydantic model)

```python
class ImageParams(BaseModel):
    size: str = "1024x1024"
    quality: Literal["low", "medium", "high"] = "high"
    output_format: str = "png"
    compression: int = 100
    n: int = 1
    input_fidelity: Literal["low", "medium", "high"] | None = None
```

No database schema changes required — `input_fidelity` is stored within the existing JSON `params` column. The `has_reference` column already exists as a boolean; the worker uses file-system glob to determine the actual count.

### 4. Frontend Changes

#### 4.1 Type Changes (`types/index.ts`)

```typescript
export interface ImageParams {
  size: string;
  quality: 'low' | 'medium' | 'high';
  output_format: string;
  compression: number;
  n: number;
  input_fidelity?: 'low' | 'medium' | 'high' | null;
}
```

#### 4.2 `ImagePromptBar` Component Changes

The component transitions from single `referenceImage: File | null` to `referenceImages: File[]`:

- Replace `<input type="file">` with `<input type="file" multiple accept="image/png,image/jpeg">`.
- Add drag-and-drop support via `onDrop` / `onDragOver` handlers.
- Display a thumbnail grid of attached images with individual remove buttons.
- Display a file count badge on the attach button.
- Conditionally show a "遮罩图（可选）" upload area when `referenceImages.length > 0`.
- Client-side validation: file type (PNG/JPEG only), size (50MB), count (max 10).
- On submit: build `FormData` with repeated `files` field entries + optional `mask`.

#### 4.3 `ImageParamsPanel` Component Changes

Add a conditional `input_fidelity` selector:

```typescript
{/* Input Fidelity - only shown in editing mode */}
{hasReferenceImages && (
  <div className="space-y-2">
    <Label htmlFor="input_fidelity">Input Fidelity</Label>
    <select
      id="input_fidelity"
      value={params.input_fidelity ?? ''}
      disabled={disabled}
      onChange={(e) => onChange({
        input_fidelity: e.target.value || null
      })}
      className={selectClass}
    >
      <option value="">Default (Azure decides)</option>
      <option value="low">Low</option>
      <option value="medium">Medium</option>
      <option value="high">High</option>
    </select>
    <p className="text-xs text-muted-foreground">
      控制输出与参考图的匹配程度
    </p>
  </div>
)}
```

#### 4.4 `ImagePlaygroundPage` State Changes

```typescript
const [referenceImages, setReferenceImages] = useState<File[]>([])
const [maskFile, setMaskFile] = useState<File | null>(null)
```

The `handleSubmit` function builds FormData with:
```typescript
referenceImages.forEach(f => formData.append('files', f))
if (maskFile) formData.append('mask', maskFile)
if (params.input_fidelity) formData.append('input_fidelity', params.input_fidelity)
```

### 5. Error Message Mapping

The backend `process_job` method classifies Azure errors before storing them:

| Azure Response | Stored `error_message` |
|---|---|
| HTTP 429 | "请求过于频繁，请稍后重试" |
| error.code == "content_policy_violation" | "内容被安全系统拦截，请修改提示词" |
| Any other non-2xx | Azure error text truncated to 500 chars |

The frontend displays `error_message` as-is in the error banner (existing behavior, no change needed).

### 6. File Persistence Layout

```
data/images/<generation_id>/
├── _reference_0.png
├── _reference_1.jpg
├── _reference_2.png
├── _mask.png          (optional)
├── 0.png              (output image 0)
├── 1.png              (output image 1)
└── ...
```

After successful processing, `_reference_*` and `_mask.png` files are cleaned up (existing cleanup pattern extended).

## Interface Contracts

### API Request: `POST /api/images/generations`

Content-Type: `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| instance_id | string | yes | Target instance ID |
| prompt | string | yes | Generation prompt |
| size | string | no | Image size (default: 1024x1024) |
| quality | string | no | low/medium/high (default: high) |
| output_format | string | no | png/jpeg/webp (default: png) |
| compression | int | no | 0-100 (default: 100) |
| n | int | no | Variations count (default: 1) |
| input_fidelity | string | no | low/medium/high (omit for Azure default) |
| files | File[] | no | Reference images (max 10, PNG/JPEG, max 50MB each) |
| mask | File | no | Mask image (PNG only, max 50MB, requires files) |
| file | File | no | Legacy single reference image (backward compat) |

### API Response (unchanged)

HTTP 202 with the same `ImageGeneration` JSON structure. The `has_reference` field is `true` when any reference images were provided.

## Error Handling

1. **Validation errors** (422/413): Returned synchronously from the API handler before enqueue.
2. **Azure errors** (during background processing): Classified and stored in `error_message` on the generation row. The worker never crashes.
3. **Network errors**: Wrapped in a descriptive message and stored as `error_message`.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Reference image count validation is consistent

*For any* set of uploaded files where the count exceeds 10, the API SHALL reject the request with HTTP 422, and no generation record SHALL be created in the database.

**Validates: Requirements 1.2, 4.6**

### Property 2: Format validation rejects non-PNG/JPEG reference images

*For any* uploaded file whose leading bytes do not match the PNG magic signature (`\x89PNG\r\n\x1a\n`) or the JPEG SOI marker (`\xff\xd8\xff`), the API SHALL reject the request with HTTP 422.

**Validates: Requirements 1.5, 4.4**

### Property 3: Mask requires at least one reference image

*For any* request that includes a mask file but zero reference images, the API SHALL reject the request with HTTP 422 with the message "使用遮罩需要至少上传一张参考图".

**Validates: Requirements 2.3**

### Property 4: Input fidelity is only forwarded in editing mode

*For any* generation request, the `input_fidelity` field SHALL appear in the outbound Azure API call if and only if at least one reference image is provided AND `input_fidelity` is explicitly set to a non-null value.

**Validates: Requirements 3.1, 3.2, 3.3**

### Property 5: Reference image persistence round-trip

*For any* set of N reference images (1 ≤ N ≤ 10) enqueued via `enqueue_generation`, persisting them to disk as `_reference_0.<ext>` through `_reference_{N-1}.<ext>` and then reading them back via `_read_all_saved_references` SHALL produce a list of N items where each item's byte content equals the original input bytes.

**Validates: Requirements 7.4, 7.5**

### Property 6: Mask persistence round-trip

*For any* valid PNG mask bytes provided to `enqueue_generation`, persisting to `_mask.png` and reading back via `_read_saved_mask` SHALL return bytes identical to the original input.

**Validates: Requirements 2.4**

### Property 7: Legacy single-file backward compatibility

*For any* request that uses the legacy `file` field (single UploadFile) without a `files` field, the system SHALL produce the same outcome as a request with `files=[file]` — specifically, a single reference image is persisted and the edits path is invoked.

**Validates: Requirements 7.1, 7.2**

### Property 8: Azure error classification is deterministic

*For any* Azure error response, the stored `error_message` SHALL be exactly "请求过于频繁，请稍后重试" when status is 429, exactly "内容被安全系统拦截，请修改提示词" when the error code is "content_policy_violation", and the truncated response text (≤ 500 characters) for all other errors.

**Validates: Requirements 6.1, 6.2, 6.3**

### Property 9: File size validation is enforced for all uploads

*For any* uploaded file (reference image or mask) whose byte length exceeds 50 × 1024 × 1024, the API SHALL reject the request with HTTP 413.

**Validates: Requirements 1.6, 2.5, 4.5**
