# grokmap MCP server in a container. Mount the repository you want to inspect:
#   docker run -i --rm -v "$PWD:/repo" grokmap
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory '*'
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[mcp]"
WORKDIR /repo
ENTRYPOINT ["grokmap-mcp"]
