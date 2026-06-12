# Third-Party Notices

Runtime and test dependencies are listed in `requirements.txt`.

Primary dependency families:

- FastAPI and Starlette for HTTP services.
- Uvicorn for local ASGI serving.
- Pydantic for request and response models.
- PyYAML for policy and persona configuration.
- HTTPX for local and Cloud Run service calls.
- pytest for tests.
- google-genai and google-auth for the optional Vertex AI Gemini cloud path.
- Playwright for final handoff screenshot verification tests.

The repository does not include third-party source bundles, vendored packages,
Google challenge PDFs, Google-branded resource-guide images, customer data, or
private third-party data.
