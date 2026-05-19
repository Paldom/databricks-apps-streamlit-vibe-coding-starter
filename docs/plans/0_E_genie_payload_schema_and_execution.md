# Implementation Plan — Reusable Genie Payload Schema + Executable Creation Flow

Purpose: provide a reusable, from-scratch Genie creation flow that does not depend on exporting or cloning any existing Genie space.

This plan defines:
- a strict payload contract for Genie serialized_space and create/update request bodies,
- payload templates with placeholders,
- executable PowerShell steps to generate valid IDs and run Databricks CLI commands,
- permission payloads for both ACL replacement and ACL patch updates.

---

## 1. Inputs

Fill these once per run:

- `PROFILE` = Databricks CLI profile (example: `adb-1272983411735654`)
- `WAREHOUSE_ID` = Pro or Serverless SQL warehouse ID
- `SPACE_TITLE` = desired Genie display title (example: `NYC Taxi Trips Genie (al)`)
- `TABLE_IDENTIFIER` = curated table/view to attach (example: `demo.nyctaxi_al.v_trips_genie`)
- `GROUP_NAME` = group to grant Genie execution access (example: `streamlit-demo-operators`)
- `DESCRIPTION` = business description shown in Genie space details

Optional:
- `PARENT_PATH` = workspace folder path for the Genie object (example: `/Users/adam.lambert@hiflylabs.com`)

---

## 2. Reusable payload contracts

### 2.1 Serialized space schema contract (minimum valid)

Databricks Genie expects serialized_space JSON with:
- `version: 2`
- `config.sample_questions[]` entries where each item includes:
  - `id`: lowercase 32-char hex string with no dashes
  - `question`: array of one or more strings
- `data_sources.tables[]` entries with `identifier`

Reference JSON Schema (for validation in tooling):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/schemas/genie-serialized-space.schema.json",
  "title": "Genie Serialized Space",
  "type": "object",
  "required": ["version", "config", "data_sources"],
  "properties": {
    "version": { "type": "integer", "const": 2 },
    "config": {
      "type": "object",
      "required": ["sample_questions"],
      "properties": {
        "sample_questions": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "object",
            "required": ["id", "question"],
            "properties": {
              "id": {
                "type": "string",
                "pattern": "^[a-f0-9]{32}$"
              },
              "question": {
                "type": "array",
                "minItems": 1,
                "items": { "type": "string", "minLength": 1 }
              }
            },
            "additionalProperties": true
          }
        }
      },
      "additionalProperties": true
    },
    "data_sources": {
      "type": "object",
      "required": ["tables"],
      "properties": {
        "tables": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "object",
            "required": ["identifier"],
            "properties": {
              "identifier": {
                "type": "string",
                "pattern": "^[^.]+\\.[^.]+\\.[^.]+$"
              }
            },
            "additionalProperties": true
          }
        }
      },
      "additionalProperties": true
    }
  },
  "additionalProperties": true
}
```

### 2.2 Genie create request contract

The CLI command `databricks genie create-space --json @file` expects:

```json
{
  "warehouse_id": "<WAREHOUSE_ID>",
  "title": "<SPACE_TITLE>",
  "description": "<DESCRIPTION>",
  "serialized_space": "<STRINGIFIED_JSON>",
  "parent_path": "<OPTIONAL_PARENT_PATH>"
}
```

Notes:
- `serialized_space` must be a JSON string (escaped), not a nested object.
- If the title already exists at target location, Databricks may append a timestamp suffix.

### 2.3 Genie update request contract

For updates:

```json
{
  "title": "<OPTIONAL_NEW_TITLE>",
  "description": "<OPTIONAL_NEW_DESCRIPTION>",
  "warehouse_id": "<OPTIONAL_NEW_WAREHOUSE_ID>",
  "serialized_space": "<OPTIONAL_STRINGIFIED_JSON>",
  "etag": "<OPTIONAL_ETAG_FOR_CONCURRENCY_CONTROL>"
}
```

Call form:

```bash
databricks genie update-space <SPACE_ID> --json @genie-update.json --profile <PROFILE> -o json
```

### 2.4 Permission payload contracts

ACL replacement payload (authoritative set):

```json
{
  "access_control_list": [
    {
      "group_name": "<GROUP_NAME>",
      "permission_level": "CAN_RUN"
    }
  ]
}
```

CLI form:

```bash
databricks permissions set genie <SPACE_ID> --json @genie-acl-set.json --profile <PROFILE> -o json
```

ACL patch payload (non-destructive add/modify):

```json
{
  "access_control_list": [
    {
      "group_name": "<GROUP_NAME>",
      "permission_level": "CAN_RUN"
    }
  ]
}
```

CLI form:

```bash
databricks permissions update genie <SPACE_ID> --json @genie-acl-update.json --profile <PROFILE> -o json
```

Recommended default: `permissions update` to avoid overwriting existing inherited/manual ACL entries.

---

## 3. Executable from-scratch creation flow (PowerShell)

Run from repository root.

### 3.1 Define runtime variables

```powershell
$PROFILE = "adb-1272983411735654"
$WAREHOUSE_ID = "1463663e9d511f7c"
$SPACE_TITLE = "NYC Taxi Trips Genie (al)"
$TABLE_IDENTIFIER = "demo.nyctaxi_al.v_trips_genie"
$GROUP_NAME = "streamlit-demo-operators"
$DESCRIPTION = "Ask questions about NYC taxi trip counts, fares, trip distances, trip durations, pickup ZIPs, dropoff ZIPs, routes, and pickup-time trends. This space uses the curated view demo.nyctaxi_al.v_trips_genie. Fare means metered fare_amount_usd only; it does not include tips, tolls, taxes, surcharges, or total amount. Location analysis is ZIP-code based. Dataset covers Jan 1 - Feb 29, 2016 (21,932 trips, 21,770 valid)."
$PARENT_PATH = ""
```

### 3.2 Build serialized_space with generated sample question IDs

```powershell
$questions = @(
  "What are the top 10 pickup ZIP codes by valid trip count?",
  "How do trips and average fare vary by hour of day?",
  "Which pickup-dropoff routes have the highest average fare with at least 20 trips?",
  "What is the average fare on weekdays versus weekends?",
  "Show fare per mile by time of day.",
  "What are the top pickup ZIPs in the latest month in the dataset?",
  "Which ZIP codes have the longest average trip distance?",
  "What is the average duration by day of week?"
)

$sampleQuestions = @()
foreach ($q in $questions) {
  $sampleQuestions += [ordered]@{
    id = ([guid]::NewGuid().ToString("N")).ToLower()
    question = @($q)
  }
}

$serializedSpaceObject = [ordered]@{
  version = 2
  config = [ordered]@{
    sample_questions = $sampleQuestions
  }
  data_sources = [ordered]@{
    tables = @(
      [ordered]@{ identifier = $TABLE_IDENTIFIER }
    )
  }
}

$serializedSpace = $serializedSpaceObject | ConvertTo-Json -Compress -Depth 20
```

### 3.3 Write create request JSON and create space

```powershell
$createReq = [ordered]@{
  warehouse_id = $WAREHOUSE_ID
  title = $SPACE_TITLE
  description = $DESCRIPTION
  serialized_space = $serializedSpace
}
if (-not [string]::IsNullOrWhiteSpace($PARENT_PATH)) {
  $createReq.parent_path = $PARENT_PATH
}

$createPath = Join-Path $PWD "genie-create.json"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($createPath, ($createReq | ConvertTo-Json -Compress -Depth 30), $utf8NoBom)

$createOutRaw = databricks genie create-space --json @genie-create.json --profile $PROFILE -o json
$createOut = $createOutRaw | ConvertFrom-Json
$SPACE_ID = $createOut.space_id

"Created SPACE_ID: $SPACE_ID"
```

### 3.4 Apply Genie permission (patch mode)

```powershell
$aclPatch = [ordered]@{
  access_control_list = @(
    [ordered]@{
      group_name = $GROUP_NAME
      permission_level = "CAN_RUN"
    }
  )
}

$aclPath = Join-Path $PWD "genie-acl-update.json"
[System.IO.File]::WriteAllText($aclPath, ($aclPatch | ConvertTo-Json -Compress -Depth 20), $utf8NoBom)

databricks permissions update genie $SPACE_ID --json @genie-acl-update.json --profile $PROFILE -o json
```

### 3.5 Verify space + attached table + ACL

```powershell
databricks genie get-space $SPACE_ID --include-serialized-space --profile $PROFILE -o json

databricks permissions get genie $SPACE_ID --profile $PROFILE -o json
```

Optional live check:

```powershell
databricks genie start-conversation $SPACE_ID --content "What are the top 3 pickup ZIP codes by valid trip count?" --profile $PROFILE -o json
```

---

## 4. Reusable payload files for agent-driven automation

Suggested tracked templates under `docs/plans/templates/`:

- `genie-serialized-space.template.json`
- `genie-create.template.json`
- `genie-update.template.json`
- `genie-acl-set.template.json`
- `genie-acl-update.template.json`

Template content examples:

### 4.1 genie-serialized-space.template.json

```json
{
  "version": 2,
  "config": {
    "sample_questions": [
      {
        "id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "question": ["Sample question"]
      }
    ]
  },
  "data_sources": {
    "tables": [
      {
        "identifier": "demo.nyctaxi_al.v_trips_genie"
      }
    ]
  }
}
```

### 4.2 genie-create.template.json

```json
{
  "warehouse_id": "1463663e9d511f7c",
  "title": "NYC Taxi Trips Genie (al)",
  "description": "Business description",
  "serialized_space": "{\"version\":2,\"config\":{\"sample_questions\":[{\"id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"question\":[\"Sample question\"]}]},\"data_sources\":{\"tables\":[{\"identifier\":\"demo.nyctaxi_al.v_trips_genie\"}]}}"
}
```

### 4.3 genie-update.template.json

```json
{
  "title": "NYC Taxi Trips Genie (al)",
  "description": "Updated description",
  "serialized_space": "{\"version\":2,\"config\":{\"sample_questions\":[{\"id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"question\":[\"Sample question\"]}]},\"data_sources\":{\"tables\":[{\"identifier\":\"demo.nyctaxi_al.v_trips_genie\"}]}}"
}
```

### 4.4 genie-acl-set.template.json

```json
{
  "access_control_list": [
    {
      "group_name": "streamlit-demo-operators",
      "permission_level": "CAN_RUN"
    }
  ]
}
```

### 4.5 genie-acl-update.template.json

```json
{
  "access_control_list": [
    {
      "group_name": "streamlit-demo-operators",
      "permission_level": "CAN_RUN"
    }
  ]
}
```

---

## 5. Failure modes and fixes

- Error: `Field 'serialized_space' is required`.
  - Cause: request body omitted `serialized_space`.
  - Fix: include stringified serialized_space in create payload.

- Error: `sample_question.id must be provided and non-empty`.
  - Cause: sample question objects missing IDs.
  - Fix: generate lowercase 32-hex IDs for each sample question.

- Error: JSON parsing with unexpected characters at first byte.
  - Cause: UTF-8 BOM in payload file.
  - Fix: write JSON files with UTF-8 without BOM.

- Title uniqueness conflict or auto-suffixing.
  - Cause: existing node/title conflict in target workspace path.
  - Fix: use unique title per operator or allow Databricks timestamp suffix.

---

## 6. Completion checklist

- New Genie space exists and returns a non-empty `space_id`.
- Serialized payload references only intended table/view identifiers.
- Group ACL includes `CAN_RUN` for target group.
- Optional smoke question returns data.
- Captured `space_id` is ready for `databricks.yml` variable wiring.
