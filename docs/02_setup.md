# 02 · Setup

## 1. Python environment (one time)

The server has Python 3.10 and `uv` (a fast package manager) but no system `pip`, so we use `uv`:

```bash
cd ~/Projects/sustainability-developer-discussion
~/.local/bin/uv venv .venv                                # creates an isolated environment in .venv/
~/.local/bin/uv pip install -p .venv -r requirements.txt  # installs requests, pandas, python-dotenv
source .venv/bin/activate                                 # do this in every new terminal
```

| Package | Used for |
|---|---|
| `requests` | sending HTTP requests to the GitHub API |
| `python-dotenv` | reading the token from the `.env` file |
| `pandas` | building and reading the CSV tables |

## 2. Create a GitHub token (one time, ~3 minutes)

A token is like a password that only lets the script *read public data*. Without one, GitHub allows
just 60 requests per hour and blocks GraphQL completely.

1. Log in to GitHub and open **https://github.com/settings/personal-access-tokens/new**
   (Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → *Generate new token*).
2. Fill in:
   - **Token name:** `sustainability-data-collection`
   - **Expiration:** 90 days (enough for the course)
   - **Resource owner:** your own account
   - **Repository access:** **Public repositories** (read-only)
   - **Permissions:** leave everything at *No access*. Public data needs no extra permissions.
3. Click **Generate token** and **copy it now**. GitHub shows it only once. It starts with `github_pat_`.
4. Put it in the project's `.env` file:
   ```bash
   cp .env.example .env
   nano .env        # replace your_token_here with the token, save with Ctrl+O, exit with Ctrl+X
   ```
   The file should contain one line: `GITHUB_TOKEN=github_pat_xxxxxxxx...`

5. Check that it works:
   ```bash
   source .env && curl -s -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/rate_limit | grep -A3 '"core"'
   ```
   You should see `"limit": 5000`.

**Safety:** `.env` is listed in `.gitignore`, so it is never committed. Never paste the token into
code, docs or chat. If it leaks, delete it on the same GitHub page and create a new one.
