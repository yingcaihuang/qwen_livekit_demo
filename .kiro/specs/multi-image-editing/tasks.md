# Implementation Plan: Multi-Image Editing

## Overview

Enhance the image generation system to support multiple reference images (up to 10), optional PNG mask uploads, and an `input_fidelity` parameter for controlling edit fidelity. Implementation proceeds backend-first (validation, persistence, Azure call changes) then frontend (multi-file UI, mask upload, params panel).

## Tasks

- [x] 1. Update backend data model and configuration
  - [x] 1.1 Add `input_fidelity` field to `ImageParams` Pydantic model in `backend/app/models/image.py`
    - Add `input_fidelity: Literal["low", "medium", "high"] | None = None` field
    - _Requirements: 3.1, 3.2_

  - [x] 1.2 Add validation helper functions in `backend/app/api/images.py`
    - Create `_is_allowed_image(file: UploadFile) -> bool` that checks magic bytes for PNG/JPEG
    - Create `_is_png(file: UploadFile) -> bool` that checks PNG magic bytes only
    - _Requirements: 1.5, 2.2_

- [x] 2. Modify backend API endpoint for multi-file support
  - [x] 2.1 Update `create_generation` endpoint signature in `backend/app/api/images.py`
    - Add `files: list[UploadFile] = File(default=[])` parameter
    - Add `mask: UploadFile | None = File(default=None)` parameter
    - Add `input_fidelity: str | None = Form(default=None)` parameter
    - Keep legacy `file: UploadFile | None = File(default=None)` parameter
    - _Requirements: 1.1, 2.1, 3.1, 7.1_

  - [x] 2.2 Implement request validation logic in `create_generation`
    - Merge legacy `file` into `files` list when `files` is empty
    - Validate file count (max 10, return 422)
    - Validate each file format via magic bytes (PNG/JPEG only, return 422)
    - Validate each file size (max 50MB, return 413)
    - Validate mask format (PNG only, return 422)
    - Validate mask size (max 50MB, return 413)
    - Validate mask requires at least one reference image (return 422)
    - _Requirements: 1.2, 1.5, 1.6, 2.2, 2.3, 2.5, 7.1_

  - [ ]* 2.3 Write property tests for endpoint validation
    - **Property 1: Reference image count validation is consistent**
    - **Property 2: Format validation rejects non-PNG/JPEG reference images**
    - **Property 3: Mask requires at least one reference image**
    - **Property 9: File size validation is enforced for all uploads**
    - **Validates: Requirements 1.2, 1.5, 1.6, 2.2, 2.3, 2.5**

- [x] 3. Modify Image_Service for multi-reference persistence and processing
  - [x] 3.1 Update `enqueue_generation` method in `backend/app/services/image_service.py`
    - Change signature to accept `reference_images: list[UploadFile | bytes] | None`
    - Accept `mask: UploadFile | bytes | None` parameter
    - Accept `input_fidelity: str | None` parameter
    - Persist multiple references as `_reference_0.<ext>`, `_reference_1.<ext>`, etc.
    - Persist mask as `_mask.png`
    - Store `input_fidelity` in the params JSON column
    - _Requirements: 7.4, 2.4, 3.1_

  - [x] 3.2 Add `_read_all_saved_references` static method
    - Glob `_reference_*` files from generation directory, sorted by index
    - Return list of `(bytes, content_type, filename)` tuples
    - _Requirements: 7.5_

  - [x] 3.3 Add `_read_saved_mask` static method
    - Read `_mask.png` from generation directory if it exists
    - Return bytes or None
    - _Requirements: 2.4_

  - [x] 3.4 Update `_call_edits` to accept multiple images, mask, and input_fidelity
    - Change signature to accept `reference_images: list[tuple[bytes, str, str]]`
    - Add each image as an `image[]` multipart field
    - Add optional `mask` multipart field
    - Add optional `input_fidelity` form field
    - _Requirements: 1.3, 2.4, 3.1_

  - [x] 3.5 Update `process_job` to use multi-reference and mask
    - Call `_read_all_saved_references` instead of `_read_saved_reference`
    - Call `_read_saved_mask` to get mask bytes
    - Extract `input_fidelity` from params dict
    - Pass all to updated `_call_edits`
    - Update `_cleanup_reference` to also remove `_mask.png`
    - _Requirements: 7.5, 2.4, 3.1, 3.3_

  - [ ]* 3.6 Write property tests for persistence round-trip
    - **Property 5: Reference image persistence round-trip**
    - **Property 6: Mask persistence round-trip**
    - **Validates: Requirements 7.4, 7.5, 2.4**

  - [ ]* 3.7 Write property test for input_fidelity forwarding
    - **Property 4: Input fidelity is only forwarded in editing mode**
    - **Validates: Requirements 3.1, 3.2, 3.3**

- [x] 4. Implement enhanced error message classification
  - [x] 4.1 Update error handling in `process_job` exception handler
    - Parse Azure response body for `error.code` field
    - Map HTTP 429 to "请求过于频繁，请稍后重试"
    - Map `content_policy_violation` to "内容被安全系统拦截，请修改提示词"
    - Truncate other errors to 500 characters
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 4.2 Write property test for error classification
    - **Property 8: Azure error classification is deterministic**
    - **Validates: Requirements 6.1, 6.2, 6.3**

- [x] 5. Checkpoint - Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Update frontend types and state management
  - [x] 6.1 Update `ImageParams` type in `frontend/src/types/index.ts`
    - Add `input_fidelity?: 'low' | 'medium' | 'high' | null` field
    - _Requirements: 3.4_

  - [x] 6.2 Update `ImagePlaygroundPage` state in `frontend/src/pages/ImagePlaygroundPage.tsx`
    - Replace `referenceImage: File | null` with `referenceImages: File[]`
    - Add `maskFile: File | null` state
    - Add `input_fidelity` to DEFAULT_PARAMS as `null`
    - Update `handleSubmit` to build FormData with repeated `files` fields, `mask`, and `input_fidelity`
    - _Requirements: 4.7, 5.5, 3.1_

- [x] 7. Implement multi-file upload UI
  - [x] 7.1 Refactor `ImagePromptBar` component for multi-file support
    - Change props from `referenceImage: File | null` to `referenceImages: File[]`
    - Change `onAttachReference` to `onAttachReferences: (files: File[]) => void` and `onRemoveReference: (index: number) => void`
    - Update file input to `multiple` with `accept="image/png,image/jpeg"`
    - Add drag-and-drop handlers (`onDrop`, `onDragOver`, `onDragLeave`)
    - Add client-side validation: format (PNG/JPEG), size (50MB), count (max 10) with toast notifications
    - Display thumbnail preview grid with individual remove buttons
    - Display file count badge on the attach button
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 7.2 Add mask upload area to `ImagePromptBar`
    - Show "遮罩图（可选）" upload area when `referenceImages.length > 0`
    - Hide when no reference images
    - Accept PNG only with validation toast
    - Show mask preview with remove button
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 8. Update `ImageParamsPanel` with input_fidelity selector
  - [x] 8.1 Add conditional `input_fidelity` select in `frontend/src/components/image/ImageParamsPanel.tsx`
    - Accept `hasReferenceImages: boolean` prop
    - Show input_fidelity selector only when `hasReferenceImages` is true
    - Options: "Default (Azure decides)", "Low", "Medium", "High"
    - _Requirements: 3.4, 3.5_

- [x] 9. Wire components together and verify backward compatibility
  - [x] 9.1 Update `ImagePlaygroundPage` to pass new props
    - Pass `referenceImages` and handlers to `ImagePromptBar`
    - Pass `maskFile` and handler to `ImagePromptBar`
    - Pass `hasReferenceImages` to `ImageParamsPanel`
    - Ensure legacy single-file path still works (test manually or via existing tests)
    - _Requirements: 7.1, 7.2, 7.3_

  - [ ]* 9.2 Write unit tests for backward compatibility
    - **Property 7: Legacy single-file backward compatibility**
    - **Validates: Requirements 7.1, 7.2**

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- The backend is implemented first (tasks 1-4) so it can be tested independently before frontend changes
- Frontend validation mirrors backend validation for immediate UX feedback; backend remains authoritative
- The legacy `file` field is preserved for backward compatibility — existing clients continue working without changes

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "3.2", "3.3"] },
    { "id": 2, "tasks": ["2.2", "3.1", "3.4"] },
    { "id": 3, "tasks": ["2.3", "3.5", "4.1"] },
    { "id": 4, "tasks": ["3.6", "3.7", "4.2"] },
    { "id": 5, "tasks": ["6.1", "6.2"] },
    { "id": 6, "tasks": ["7.1", "8.1"] },
    { "id": 7, "tasks": ["7.2", "9.1"] },
    { "id": 8, "tasks": ["9.2"] }
  ]
}
```
