FROM python:3.11-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml README.md langgraph.json .env.example /app/
COPY src /app/src
RUN uv pip install -e .
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "agent_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
