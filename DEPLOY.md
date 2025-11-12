Sync files (may be already running in background):
```databricks sync --watch . /Workspace/Shared/streamlit-demo```

Deploy project:
```databricks apps deploy streamlit-demo --source-code-path /Workspace/Shared/streamlit-demo```