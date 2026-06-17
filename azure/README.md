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

The VM's cloud-init installs Docker + the Compose plugin and
registers a `airs.service` systemd unit that runs `docker compose up -d --build`
in that directory. **It does not bake in your app files or secrets** — you copy those
up in step 3 (keeps the 42 KB `index.html` and your Prisma key out of the template).

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

### 3. Copy the application onto the VM

Run from the repo root (`~/AIRS`). This sends the app payload plus the
Azure-tuned compose + nginx config into `/home/jkwisda/azure`:

```sh
FQDN=<fqdn-from-output>

rsync -av \
  backend index.html .env \
  azure/docker-compose.yml azure/nginx.conf \
  jkwisda@$FQDN:/home/jkwisda/azure/
```

> `.env` carries your Prisma AIRS key — it travels over SSH, never through the
> ARM template. (Consider rotating the key that's currently committed in `.env`.)

### 4. Add your permitted IPs to nginx, then start

SSH in and edit the nginx allowlist:

```sh
ssh jkwisda@$FQDN
sudo nano /home/jkwisda/azure/nginx.conf   # add `allow`-style entries in the geo{} block
sudo systemctl start airs.service
```

First start builds the backend image and pulls Ollama — give it a minute.

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

```sh
cd /home/jkwisda/azure
docker compose ps                 # status
docker compose logs -f backend    # tail backend logs
docker compose restart web        # after editing nginx.conf
docker compose pull && docker compose up -d   # update images
```

## Notes

- **Sizing:** default `Standard_D4s_v5` (4 vCPU / 16 GB) is CPU-only and fine for
  small models. For bigger models bump `vmSize`, or pick an `NC`-series GPU size
  and uncomment the GPU block in `docker-compose.yml` (also install the NVIDIA
  container toolkit on the host).
- **Disk:** Ollama models are large; the OS disk defaults to 128 GB Premium SSD.
- **TLS:** the edge is HTTP only. To add HTTPS, drop a cert into `/home/jkwisda/azure/certs`,
  add a `listen 443 ssl;` server block to `nginx.conf`, and uncomment the 443
  port + cert mount in `docker-compose.yml`.
```
