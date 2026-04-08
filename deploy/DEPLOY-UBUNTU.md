# Deploy cogo-mcp on Ubuntu (`/mcp/cogo`)

Run the app **behind nginx**: bind the MCP server to **localhost only**, expose it on **`https://your-server/mcp/cogo`** (or HTTP) via nginx. Run the process under **systemd** so it restarts on failure and after reboot.

## Deploy under `~/mcp` (home folder)

If your server keeps MCP projects in **`~/mcp`** (e.g. `/home/ubuntu/mcp`), clone **into that directory** — do **not** use `/mcp/cogo` unless you created `/mcp` at the filesystem root.

```bash
cd ~/mcp
git clone https://github.com/Charley-Forey-AI/cogo-mcp.git cogo
```

App root is then **`~/mcp/cogo`** (i.e. `/home/ubuntu/mcp/cogo`). Use that path for **venv**, **`.env`**, and **systemd** `WorkingDirectory` / `ExecStart`. Nginx still proxies to `127.0.0.1:8880`; only filesystem paths change.

The steps below use **`/mcp/cogo`** as an example; substitute **`/home/ubuntu/mcp/cogo`** (or your user’s home) everywhere if you use `~/mcp`.

## 1. System user and directory

```bash
sudo mkdir -p /mcp
sudo useradd --system --home /mcp --shell /usr/sbin/nologin mcp 2>/dev/null || true
sudo chown mcp:mcp /mcp
```

## 2. Clone or update the repo

```bash
sudo -u mcp git clone https://github.com/Charley-Forey-AI/cogo-mcp.git /mcp/cogo
# Later updates:
# sudo -u mcp git -C /mcp/cogo pull
```

## 3. Python venv and dependencies

```bash
sudo -u mcp python3 -m venv /mcp/cogo/.venv
sudo -u mcp /mcp/cogo/.venv/bin/pip install --upgrade pip
sudo -u mcp /mcp/cogo/.venv/bin/pip install -r /mcp/cogo/requirements.txt
```

## 4. Environment file

```bash
sudo -u mcp cp /mcp/cogo/.env.example /mcp/cogo/.env
sudo -u mcp nano /mcp/cogo/.env   # or vim
chmod 600 /mcp/cogo/.env
```

Set at least:

| Variable | Example |
|----------|---------|
| `OPENAI_API_KEY` | your key |
| `OPENAI_FINETUNED_MODEL` | `ft:gpt-4.1-nano-2025-04-14:trimble:project1:DDahEMRm` |
| `FASTMCP_HOST` | `127.0.0.1` (only listen on localhost; nginx is public) |
| `FASTMCP_PORT` | `8880` (must match nginx `proxy_pass`) |
| `FASTMCP_STREAMABLE_HTTP_PATH` | `/mcp/cogo` (must match nginx `location`) |

**MCP URL used by clients** (after nginx):

`https://<your-server-domain>/mcp/cogo`

## 5. systemd service

```bash
sudo cp /mcp/cogo/deploy/cogo-mcp.service /etc/systemd/system/cogo-mcp.service
sudo systemctl daemon-reload
sudo systemctl enable --now cogo-mcp
sudo systemctl status cogo-mcp
```

Logs:

```bash
journalctl -u cogo-mcp -f
```

## 6. nginx

Edit your existing `server { ... }` and add the `location /mcp/cogo { ... }` block from `deploy/nginx-cogo-mcp.conf.example` (uncomment and fix `server_name` / SSL if needed). Ensure `proxy_pass` port matches `FASTMCP_PORT`.

Test and reload:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## 7. Firewall

If `ufw` is enabled, allow HTTP/HTTPS only (not 8880 publicly):

```bash
sudo ufw allow 'Nginx Full'
# Do not expose 8880 to the internet if the app binds to 127.0.0.1
```

## Troubleshooting

- **502 Bad Gateway** — Service not running: `systemctl status cogo-mcp`. Wrong port/path: compare `.env` and nginx `proxy_pass` / `location`.
- **Connection refused** — Confirm `FASTMCP_HOST=127.0.0.1` and `FASTMCP_PORT` matches nginx.
- **Wrong path** — `FASTMCP_STREAMABLE_HTTP_PATH` must be exactly `/mcp/cogo` if clients call `https://host/mcp/cogo`.
