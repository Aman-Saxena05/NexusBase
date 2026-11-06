# NexusBase eval results

- Run at: 2026-11-06T10:53:30+00:00
- API: `http://localhost:8000` · access_level: `public`
- Questions file status: **DRAFT**
- **Retrieval hit rate: 0/20 = 0.00**
- **Keyword pass rate: 0/20 = 0.00**
- Errors: 20

Retrieved sources are the `chunks[].source` values returned by `/v1/query`. NexusBase returns only the chunks its grader judged relevant, so a miss can come from either search or grading.

| id | expected_source | hit | keywords | missing keywords | retrieved sources | status |
|---|---|---|---|---|---|---|
| q01 | background-tasks.md | ❌ | ❌ | BackgroundTasks, add_task | (none) | error 500 |
| q02 | cors.md | ❌ | ❌ | CORSMiddleware, allow_origins | (none) | error 500 |
| q03 | response-status-code.md | ❌ | ❌ | status_code | (none) | error 500 |
| q04 | handling-errors.md | ❌ | ❌ | HTTPException, raise | (none) | error 500 |
| q05 | static-files.md | ❌ | ❌ | StaticFiles, mount | (none) | error 500 |
| q06 | testing.md | ❌ | ❌ | httpx | (none) | error 500 |
| q07 | path-params.md | ❌ | ❌ | Enum | (none) | error 500 |
| q08 | query-params.md | ❌ | ❌ | skip, limit, 10 | (none) | error 500 |
| q09 | request-files.md | ❌ | ❌ | UploadFile, spooled | (none) | error 500 |
| q10 | request-forms.md | ❌ | ❌ | username, password, form | (none) | error 500 |
| q11 | middleware.md | ❌ | ❌ | @app.middleware("http") | (none) | error 500 |
| q12 | encoder.md | ❌ | ❌ | jsonable_encoder, dict | (none) | error 500 |
| q13 | body-updates.md | ❌ | ❌ | PATCH, exclude_unset | (none) | error 500 |
| q14 | header-params.md | ❌ | ❌ | convert_underscores, hyphen | (none) | error 500 |
| q15 | cookie-params.md | ❌ | ❌ | Cookie | (none) | error 500 |
| q16 | response-model.md | ❌ | ❌ | response_model | (none) | error 500 |
| q17 | metadata.md | ❌ | ❌ | openapi_tags | (none) | error 500 |
| q18 | sql-databases.md | ❌ | ❌ | SQLModel, SQLAlchemy | (none) | error 500 |
| q19 | bigger-applications.md | ❌ | ❌ | APIRouter, include_router | (none) | error 500 |
| q20 | path-params-numeric-validations.md | ❌ | ❌ | Path, ge=1 | (none) | error 500 |
