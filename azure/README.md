# Deploying a simple AI Chat Application to Azure for demo purposes

This folder lifts the AIRS app (Ollama + Flask backend + nginx edge) onto a single
**Ubuntu 24.04 VM with Docker** and a **public IP**. No PaaS / "fancy" Azure services
are used — just a VM, a NIC, a public IP, a VNet, and a Network Security Group.


## What gets created

| Resource | Purpose |
|---|---|
| `Microsoft.Compute/virtualMachines` | Ubuntu 24.04 LTS, Docker installed via cloud-init |
| `Microsoft.Network/publicIPAddresses` | Static public IP + DNS name |
| `Microsoft.Network/networkSecurityGroups` | First IP allowlist (ports 22/80/443) |
| `Microsoft.Network/virtualNetworks` + subnet | VM network |
| `Microsoft.Network/networkInterfaces` | VM NIC |

The VM's cloud-init installs Docker + the Compose plugin. **It does not bake in
your app files or secrets** — you bring the repo up in step 3 (keeps the 42 KB
`index.html` and your Prisma key out of the template).

> The template also writes an `airs.service` systemd unit that runs a bare
> `docker compose up -d --build` in `/home/jkwisda/azure`. That reflects the
> older flat-copy layout. The current workflow instead git-pulls the whole repo
> and runs `docker compose -f docker-compose.azure.yml ...` from the repo root
> (see below), so either disable that unit or update its `WorkingDirectory` +
> `ExecStart` to match your clone path.

## Two layers of IP allowlisting

1. **Azure NSG** — `sshSourceAddressPrefix` / `httpSourceAddressPrefix` parameters.
2. **nginx** — the `geo $allowed { ... }` block in `nginx.conf`.

Set both to your own IP. The NSG drops traffic at the network edge; nginx is the
in-app backstop you asked for.

---

## Deploy

### 1. Fill in parameters

Edit `azuredeploy.parameters.json`:

- `adminPublicKey` → contents of your SSH public key (`cat ~/.ssh/id_ed25519.pub`)
- `sshSourceAddressPrefix` → `YOUR.PUBLIC.IP/32` (find it: `curl -s ifconfig.me`)
- `httpSourceAddressPrefix` → `YOUR.PUBLIC.IP/32`

### 2. Create the resource group and deploy

```sh
az group create --name airs-rg --location westeurope

az deployment group create \
  --resource-group airs-rg \
  --template-file azuredeploy.json \
  --parameters @azuredeploy.parameters.json
```

Note the `fqdn` / `publicIP` / `sshCommand` outputs at the end.

### 3. Get the repo onto the VM

The app is a single source of truth in this repo — the Azure edge and the Caddy
host share the same `backend/` and `index.html`. On the VM, clone (first time)
or pull (updates) the repo and run the **Azure** compose file from its root:

```sh
FQDN=<fqdn-from-output>
ssh jkwisda@$FQDN

# first time:
git clone git@github.com:kassemmel/FREE-REAL-ESTATE.git ~/azure
# updates thereafter:
cd ~/azure && git pull
```

`.env` (with your Prisma AIRS key) is gitignored, so copy it up once out of band
— e.g. `scp .env jkwisda@$FQDN:~/azure/.env`. It never travels through the ARM
template. (Consider rotating the key that's currently committed in `.env`.)

> The compose files use `${VAR:-default}` interpolation and auto-load `.env` from
> the directory you run them in, so keep `.env` at the repo root on the VM.

### 4. Add your permitted IPs to nginx, then start

Edit the nginx allowlist, then bring the stack up from the repo root:

```sh
cd ~/azure
nano azure/nginx.conf          # add `allow`-style entries in the geo{} block
docker compose -f docker-compose.azure.yml up -d --build
```

First start builds the backend image and pulls Ollama — give it a minute.
(n8n and stocks-mcp are Caddy-host-only and deliberately absent from this stack.)

### 5. Pull a model

Ollama starts empty. Pull whatever model the app expects:

```sh
docker exec -it bleepbloopbot-ollama ollama pull llama3.2
```

### 5b. (Optional) Add an Azure AI Foundry model

Ollama and Azure run side by side — Foundry models just show up in the same model
dropdown, prefixed `azure/`. To enable, put these in `/home/jkwisda/azure/.env`:

```sh
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/openai/v1   # v1 (OpenAI-compatible)
AZURE_OPENAI_API_KEY=<key from the Foundry resource>
AZURE_OPENAI_API_VERSION=2024-10-21      # only used for the classic (non-/openai/v1) endpoint
AZURE_OPENAI_DEPLOYMENTS=gpt-o4          # comma-separated deployment names
```

Then `docker compose up -d backend`. The deployment appears as `azure/gpt-o4` in the UI;
selecting it routes that chat to Azure (still scanned by Prisma AIRS), while plain
Ollama models keep routing to the local container. Leave the vars blank to hide it.

> `AZURE_OPENAI_DEPLOYMENTS` is the **deployment name** you chose in the Foundry portal,
> not the base model id. If you deployed an `o`-series reasoning model, responses can be
> slower and the model ignores `temperature`; no code change needed.

### 6. Use it

Open `http://<fqdn>` from an allowlisted IP.

---

## Day-2 operations

Run these from the repo root, always with `-f docker-compose.azure.yml`:

```sh
cd ~/azure
docker compose -f docker-compose.azure.yml ps                 # status
docker compose -f docker-compose.azure.yml logs -f backend    # tail backend logs
docker compose -f docker-compose.azure.yml restart web        # after editing azure/nginx.conf
git pull && docker compose -f docker-compose.azure.yml up -d --build   # deploy latest code
```

## Notes

- **Sizing:** default `Standard_D4s_v5` (4 vCPU / 16 GB) is CPU-only and fine for
  small models. For bigger models bump `vmSize`, or pick an `NC`-series GPU size
  and uncomment the GPU block in `docker-compose.yml` (also install the NVIDIA
  container toolkit on the host).
- **Disk:** Ollama models are large; the OS disk defaults to 128 GB Premium SSD.
- **TLS:** `docker-compose.azure.yml` wires up Let's Encrypt via certbot. `azure/nginx.conf`
  is the port-80 bootstrap config used to obtain the first cert; issue it once with:
  ```sh
  docker compose -f docker-compose.azure.yml run --rm certbot certonly --webroot \
    -w /var/www/certbot -d <your-fqdn> --email kassemmel@protonmail.com --agree-tos --no-eff-email
  ```
  Then swap in the TLS server block (`cp azure/nginx.conf.https azure/nginx.conf` and
  `docker compose -f docker-compose.azure.yml restart web`). The `certbot-renew` service
  renews automatically and the `web` container reloads every 6h to pick up new certs.
```
