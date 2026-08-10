# Requirements Document

## Introduction

Enhance the existing Azure OpenAI image generation feature to support multiple reference images, mask-based editing, and an `input_fidelity` parameter. The backend must accept up to 10 reference images via a multipart `files` field, an optional PNG mask, and route them to the Azure Images edits API with correct multipart encoding. The frontend must provide multi-file upload with previews, mask upload in editing mode, and improved error messaging for Azure-specific failures. All changes must remain backward-compatible with the existing single-file (`file` field) upload path.

## Glossary

- **Image_Service**: The backend service layer (`image_service.py`) responsible for Azure API calls, file persistence, and job lifecycle management.
- **Images_API**: The FastAPI router (`images.py`) exposing REST endpoints for image generation, retrieval, and deletion.
- **Image_Prompt_Bar**: The frontend component handling prompt input and reference image attachment.
- **Image_Params_Panel**: The frontend component displaying generation parameter controls (compression, format, variations).
- **Azure_Edits_API**: The Azure OpenAI Images edits endpoint (`/openai/v1/images/edits`) that accepts reference images and an optional mask.
- **Azure_Generations_API**: The Azure OpenAI Images generations endpoint (`/openai/v1/images/generations`) for text-to-image without references.
- **Reference_Image**: An uploaded image file used as input context for the Azure edits operation.
- **Mask**: An optional PNG image where transparent regions indicate areas to be edited by the Azure edits operation.
- **Input_Fidelity**: An optional parameter (low/medium/high) controlling how closely the output matches the reference image(s) in editing mode.

## Requirements

### Requirement 1: Multi-Reference Image Upload (Backend)

**User Story:** As a developer testing image editing, I want to upload multiple reference images in a single request, so that I can leverage Azure's multi-image editing capabilities.

#### Acceptance Criteria

1. WHEN a request to POST `/api/images/generations` includes one or more files in the `files` field, THE Images_API SHALL accept up to 10 UploadFile entries and pass them to Image_Service for processing.
2. WHEN the number of uploaded reference images exceeds 10, THE Images_API SHALL return HTTP 422 with the message "参考图最多 10 张".
3. WHEN one or more reference images are provided, THE Image_Service SHALL call the Azure_Edits_API with each image sent as a separate `image[]` multipart field.
4. WHEN no reference images are provided, THE Image_Service SHALL call the Azure_Generations_API using the existing text-to-image path.
5. WHEN a reference image has a file format other than PNG or JPEG, THE Images_API SHALL return HTTP 422 with the message "仅支持 PNG 和 JPG 格式".
6. WHEN a single reference image exceeds 50 MB, THE Images_API SHALL return HTTP 413 with the message "图片大小不能超过 50MB".

### Requirement 2: Mask Upload (Backend)

**User Story:** As a developer testing inpainting, I want to upload an optional mask image alongside reference images, so that I can control which regions of the image are edited.

#### Acceptance Criteria

1. WHEN a request includes a `mask` file field, THE Images_API SHALL accept the mask UploadFile and pass it to Image_Service.
2. WHEN the mask file is not in PNG format, THE Images_API SHALL return HTTP 422 with the message "遮罩图必须是 PNG 格式".
3. WHEN a mask is provided without any reference images, THE Images_API SHALL return HTTP 422 with the message "使用遮罩需要至少上传一张参考图".
4. WHEN a mask is provided with reference images, THE Image_Service SHALL include the mask as the `mask` multipart field in the Azure_Edits_API call.
5. WHEN the mask exceeds 50 MB, THE Images_API SHALL return HTTP 413 with the message "遮罩图大小不能超过 50MB".

### Requirement 3: Input Fidelity Parameter

**User Story:** As a developer testing image editing, I want to control how closely the output matches my reference images, so that I can fine-tune the editing behavior.

#### Acceptance Criteria

1. WHEN a request includes the `input_fidelity` parameter with a value of "low", "medium", or "high", THE Image_Service SHALL include `input_fidelity` in the Azure_Edits_API call body.
2. WHEN `input_fidelity` is not provided, THE Image_Service SHALL omit the field from the Azure API call, allowing Azure to use its default value.
3. WHEN `input_fidelity` is provided but no reference images are present (generations mode), THE Image_Service SHALL ignore the `input_fidelity` parameter and proceed with the generations call.
4. WHILE the frontend is in editing mode (reference images are attached), THE Image_Params_Panel SHALL display an input_fidelity selector with options "Low", "Medium", and "High".
5. WHILE the frontend is in generation mode (no reference images attached), THE Image_Params_Panel SHALL hide the input_fidelity selector.

### Requirement 4: Multi-File Upload UI

**User Story:** As a user, I want to select or drag multiple reference images with visual feedback, so that I can easily prepare a multi-image editing request.

#### Acceptance Criteria

1. THE Image_Prompt_Bar SHALL support selecting multiple image files via click or drag-and-drop.
2. WHEN files are selected, THE Image_Prompt_Bar SHALL display a thumbnail preview list showing each attached image with an individual remove button.
3. WHEN files are selected, THE Image_Prompt_Bar SHALL display a badge showing the count of attached images.
4. WHEN a user selects a file that is not PNG or JPEG, THE Image_Prompt_Bar SHALL display a toast notification with the message "仅支持 PNG 和 JPG 格式" and reject that file.
5. WHEN a user selects a file exceeding 50 MB, THE Image_Prompt_Bar SHALL display a toast notification with the message "图片大小不能超过 50MB" and reject that file.
6. WHEN the user attempts to attach more than 10 images total, THE Image_Prompt_Bar SHALL display a toast notification with the message "参考图最多 10 张" and reject the excess files.
7. WHEN generating, THE Image_Prompt_Bar SHALL send each reference image as a repeated `files` field in the FormData request.

### Requirement 5: Mask Upload UI

**User Story:** As a user, I want to optionally upload a mask image when reference images are present, so that I can specify regions to edit.

#### Acceptance Criteria

1. WHILE reference images are attached, THE Image_Prompt_Bar SHALL display a "遮罩图（可选）" upload area.
2. WHILE no reference images are attached, THE Image_Prompt_Bar SHALL hide the mask upload area.
3. WHEN a user selects a mask file that is not PNG format, THE Image_Prompt_Bar SHALL display a toast notification with the message "遮罩图必须是 PNG 格式" and reject the file.
4. WHEN a mask is attached, THE Image_Prompt_Bar SHALL display a preview of the mask with a remove button.
5. WHEN generating with a mask attached, THE Image_Prompt_Bar SHALL include the mask as the `mask` field in the FormData request.

### Requirement 6: Enhanced Error Messages

**User Story:** As a user, I want clear error messages for Azure-specific failures, so that I can understand what went wrong and how to fix it.

#### Acceptance Criteria

1. WHEN the Azure API returns a `content_policy_violation` error, THE Image_Service SHALL surface the message "内容被安全系统拦截，请修改提示词" in the generation record's error_message field.
2. WHEN the Azure API returns HTTP 429, THE Image_Service SHALL surface the message "请求过于频繁，请稍后重试" in the generation record's error_message field.
3. WHEN the Azure API returns any other error, THE Image_Service SHALL surface the Azure error response text (truncated to 500 characters) in the generation record's error_message field.

### Requirement 7: Backward Compatibility

**User Story:** As a user of the existing system, I want my current workflows to continue functioning after this update, so that nothing breaks.

#### Acceptance Criteria

1. WHEN a request uses the legacy `file` field (single UploadFile), THE Images_API SHALL treat it as a single reference image and proceed with the edits path.
2. WHEN no reference images and no `file` field are provided, THE Images_API SHALL proceed with the generations path.
3. THE Image_Service queue mechanism, history list endpoint, and generation detail endpoint SHALL continue to function without modification to their response schemas.
4. THE Image_Service SHALL persist multiple reference images to disk as `_reference_0.<ext>`, `_reference_1.<ext>`, etc., within the generation directory.
5. WHEN processing a queued job with multiple saved references, THE Image_Service SHALL read all `_reference_*` files and include them in the Azure_Edits_API call.
