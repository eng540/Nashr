# Nashr Image Generation Provider Boundary

Status: implementation proposal represented by the provider-neutral adapter code in this branch.

## Goal

Nashr's image-production recipe must not depend on a single model, vendor, or API shape. The recipe capability, Artifact contract, private storage, review flow, and publication flow remain stable while provider-specific request/response details stay inside adapters.

## Runtime path

Production Recipe Stage
→ `ProduceImageArtifactCapability`
→ `create_image_generator(stage_configuration)`
→ stable `ImageGenerator.generate(prompt, aspect_ratio, image_size)` port
→ selected adapter (`gemini` or `fal`)
→ validated image bytes
→ private Artifact Storage
→ IMAGE Artifact in DRAFT review state
→ human review/approval

The capability and Artifact contract do not import or expose fal.ai SDK objects or Gemini SDK response types.

## Provider/model selection

Selection precedence:
1. Pinned recipe-stage configuration: `provider` and `model`.
2. Deployment defaults: `IMAGE_GENERATION_PROVIDER` and `IMAGE_GENERATION_MODEL`.
3. Gemini compatibility default when no provider is configured.

Example recipe-stage configuration:

```json
{
  "provider": "fal",
  "model": "fal-ai/nano-banana-2",
  "aspect_ratio": "16:9",
  "image_size": "2K"
}
```

The fal adapter maps the shared options to endpoint-specific request fields inside the adapter. Recipe configuration does not contain provider SDK payloads or arbitrary endpoint-specific options. When a new endpoint needs a different request schema, the change is limited to the selected provider adapter and its tests.

To select fal at deployment level, configure `IMAGE_GENERATION_PROVIDER=fal`, `IMAGE_GENERATION_MODEL=fal-ai/nano-banana-2`, and a secret `FAL_KEY`. The key must remain server-side and must never be exposed to the browser or logged.

To switch back to Gemini, set `IMAGE_GENERATION_PROVIDER=gemini` and configure `GEMINI_API_KEY` plus `GEMINI_IMAGE_MODEL`. No production capability or Artifact code needs to change.

## Reliability and safety

- The image capability checks private object storage before making a paid generation request.
- The provider adapter normalizes results to bytes, MIME type, provider name, and model ID.
- fal result URLs are restricted to HTTPS and known fal/Google storage hosts; redirects are disabled.
- Image downloads have a 20 MiB bound and MIME/signature validation.
- Provider credentials stay in server environment variables.
- Generated media is stored in private object storage; only a short-lived presigned URL is returned for review.
- Existing artifact idempotency/retry behavior and DRAFT review gate remain unchanged.

## Important limitations

- A common port does not make all model-specific options identical. Endpoint-specific parameters belong in the selected adapter and its tests.
- Provider selection through environment variables is a deployment default. For per-recipe model management, store `provider` and `model` in the versioned recipe stage configuration so a production run pins the selected configuration.
- This branch adds a fal adapter but cannot prove a live generation without a valid `FAL_KEY` and a funded fal account. CI/unit tests prove provider selection and local validation only; a real Railway run is still required to prove external API access, billing, storage, and review UI end-to-end.
- This change does not publish anything to Telegram.
