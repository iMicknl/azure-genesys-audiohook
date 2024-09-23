FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
COPY . /app

# - Silence uv complaining about not being able to use hard links,
# - tell uv to byte-compile packages for faster application startups,
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# ENV UV_PROJECT_ENVIRONMENT=/app

# Sync the project into a new environment, using the frozen lockfile
RUN uv sync --frozen --no-dev --no-install-project

# Expose the port the app runs on
EXPOSE 8000

# Command to run the Quart app with gunicorn (/w uvicorn workers)
CMD ["uv", "run", "gunicorn", "-b", "0.0.0.0:8000", "app:app"]
