# Fact Check

> Review date: 2026-06-10
> Scope: AutoDL platform facts, ComfyUI ecosystem, download/network/security facts.

## AutoDL Platform

| Topic | Finding | Source |
|---|---|---|
| Instance data retention | AutoDL docs state that as long as the instance exists, data remains across start/stop and subscription expiry, but a continuously stopped instance has a 15-day release cycle; once released, all instance data is cleared and cannot be restored. This makes Git-backed `model-lock.yaml` mandatory. | [AutoDL instance data](https://www.autodl.com/docs/instance_data/) |
| Local data disk reliability | AutoDL describes system/data disks as generally local SSD, with no redundancy guarantee for local disks; important data should be backed up externally. This supports treating `/root/autodl-tmp/models` as local fact but not durable backup. | [AutoDL local disk](https://www.autodl.com/docs/local_disk/) |
| Default data disk | AutoDL local disk docs say rented instances include a free 50GB data disk by default, and paid expansion is charged even if the instance is shut down until release/shrink. | [AutoDL local disk](https://www.autodl.com/docs/local_disk/) |
| Ports 6006/6008 | AutoDL maps only 6006 and 6008 to public `ip:port`, with TCP or HTTP selectable. Personal users may need SSH tunnel for arbitrary ports. The docs show service examples using `127.0.0.1:6006`, so current `--listen 127.0.0.1` is likely acceptable, but should still be verified on actual custom-service HTTP mode. | [AutoDL open port](https://www.autodl.com/docs/port/), [AutoDL SSH tunnel](https://www.autodl.com/docs/ssh_proxy/) |
| Academic acceleration | AutoDL built-in acceleration explicitly covers `github.com`, `githubusercontent.com`, `githubassets.com`, and `huggingface.co`, loaded by `source /etc/network_turbo`; it also says no stability guarantee. The project fallback design is aligned. | [AutoDL network_turbo](https://www.autodl.com/docs/network_turbo/) |
| No-GPU mode | AutoDL no-GPU mode runs with `0.5` CPU, `2GB` memory, no GPU, `￥0.1/hour`, preserves data, and only one such instance is allowed under a main account. It can free the GPU, so returning to GPU mode may hit capacity shortage. | [AutoDL save money](https://www.autodl.com/docs/save_money/) |
| Instance billing | Pay-as-you-go billing starts when instance is on and stops when shut down; data is retained after shutdown for a period, but GPU is not reserved. This reinforces the value of fast no-GPU setup and explicit `bye` sync. | [AutoDL price](https://www.autodl.com/docs/price/) |
| File storage alternative | AutoDL file storage has a 20GB free threshold and charges by usage above it. It is a plausible external durable store for future model backup guidance, not a default dependency. | [AutoDL price](https://www.autodl.com/docs/price/) |

## ComfyUI Ecosystem

| Topic | Finding | Source |
|---|---|---|
| ComfyUI Manager snapshots | ComfyUI-Manager saves snapshots under the Manager user directory, supports restore, but notes non-Git custom nodes have incomplete snapshot support. This matches the project using snapshots as a convenience, not a perfect lock. | [ComfyUI-Manager README](https://github.com/Comfy-Org/ComfyUI-Manager) |
| Manager path changed | Manager v0.3.76+ uses `<USER_DIRECTORY>/__manager/`, while older versions used `<USER_DIRECTORY>/default/ComfyUI-Manager/`. Current project example uses `user/__manager`, which is aligned with newer Manager. | [ComfyUI-Manager README](https://github.com/Comfy-Org/ComfyUI-Manager) |
| comfy-cli commands | `comfy-cli` supports `save-snapshot`, `restore-snapshot`, `install-deps --workflow`, `deps-in-workflow --workflow`, `uv-sync`, and `comfy model download/list/remove`. The project should reuse these before adding custom workflow parsers. | [comfy-cli README](https://github.com/Comfy-Org/comfy-cli) |
| comfy-cli model download | `comfy model download` accepts CivitAI/HuggingFace URLs, relative paths, and transient tokens from env vars. The project still has value because it adds AutoDL network strategy, Git roaming, and model-lock semantics, but command naming should not conflict. | [comfy-cli README](https://github.com/Comfy-Org/comfy-cli) |
| Model path config | ComfyUI still documents `extra_model_paths.yaml.example`, including central model folders and multiple model categories. The project's symlink-only approach is valid for one AutoDL workspace, but extra_model_paths remains the official cross-workspace/cross-UI escape hatch. | [ComfyUI extra_model_paths.yaml.example](https://raw.githubusercontent.com/Comfy-Org/ComfyUI/master/extra_model_paths.yaml.example) |

## Download Strategy

| Topic | Finding | Source |
|---|---|---|
| HuggingFace cache locations | `huggingface_hub` defaults caches under `~/.cache/huggingface` unless `HF_HOME`/cache env vars are set. README's claim that `.cache` is redirected is false in current code and matters for system disk pressure. | [HF hub env vars](https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables) |
| hf_transfer | HF docs mark `HF_HUB_ENABLE_HF_TRANSFER` deprecated because file transfers now go through `hf-xet`; current project should not promise hf_transfer/hf_xet recovery unless real AutoDL tests prove it. | [HF hub env vars](https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables) |
| hf_xet behavior | HF docs expose `HF_XET_*` env vars and say `hf-xet` is used automatically when available. This does not imply aria2 backend support in `huggingface_hub`. | [HF hub env vars](https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables) |
| HF mirror | `hf-mirror.com` documents `HF_ENDPOINT=https://hf-mirror.com`, supports `huggingface-cli`, and provides `hfd`, which is explicitly based on `aria2`. This supports the project's aria2-first decision. | [HF-Mirror](https://hf-mirror.com/) |
| Gated HF repos | `hf-mirror.com` says gated repos still require approval on HuggingFace official site and an access token. Project docs should say token solves auth, not entitlement. | [HF-Mirror](https://hf-mirror.com/) |
| CivitAI docs | The old CivitAI GitHub wiki says API docs moved to `developer.civitai.com`. I found no authoritative public fixed rate-limit number in the accessible docs; treat CivitAI rate limits as platform-controlled and handle 401/403/429 with actionable messages. | [CivitAI REST wiki](https://github.com/civitai/civitai/wiki/REST-API-Reference) |

## Network / Proxy

| Topic | Finding | Source |
|---|---|---|
| mihomo service pattern | Official/community mihomo docs support running it as a Linux service or long-running process. Current direct process + PID/log file is acceptable for a personal root instance; systemd would add durability but also more lifecycle surface. | [mihomo docs](https://wiki.metacubex.one/startup/service/) |
| Subscription URL risk | Clash/mihomo subscription URL functions as a bearer secret: anyone with it can usually fetch proxy config. The project stores `subscription_url` in gitignored `secrets.yaml`, which is correct; docs should explicitly warn not to put it in `userdata_repo`. | Inferred from subscription design; no stable official security note found. |
| AutoDL proxy policy | I did not find a direct AutoDL doc forbidding local outbound proxy clients. Keep this as an Open Question if exposing proxy or tunneling traffic beyond the instance. | Not confirmed. |

## Security / Credentials

| Topic | Finding | Source |
|---|---|---|
| Deploy key tradeoff | GitHub deploy keys are repository-scoped and read-only by default, but write access can be granted; drawbacks include no expiry and easy access if the server is compromised. Good default for a one-repo userdata backup only if documented with rotation. | [GitHub deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys) |
| PAT tradeoff | GitHub says PATs should be treated like passwords and recommends fine-grained PATs over classic PATs when possible. PATs are worse than deploy keys for a personal AutoDL box unless the user needs multi-repo access. | [GitHub PAT docs](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) |
| GitHub App | GitHub recommends Apps for fine-grained control; installation tokens can be tightly scoped and expire after one hour. This is robust but overkill for this personal tool today. | [GitHub deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys) |
| Secret scanning | GitHub secret scanning detects exposed credentials and can notify providers; public repositories get scanning for free. This is mitigation, not permission to store secrets in Git. | [GitHub secret scanning](https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning) |
| Leak prevalence | GitGuardian reported 23,770,171 new secrets detected in public GitHub commits in 2024, and 70% of secrets leaked in 2022 were still valid. `.gitignore` must be treated as necessary but insufficient. | [GitGuardian 2025 report](https://www.gitguardian.com/state-of-secrets-sprawl-report-2025) |

## Unconfirmed Items

- Exact current AutoDL mainstream PyTorch/CUDA image matrix: docs are image-specific and dynamic; do not bake a fixed version table into this repo.
- CivitAI exact API rate-limit quotas: accessible docs did not expose a stable numeric limit.
- Whether AutoDL custom-service HTTP mode requires service binding to `0.0.0.0`: AutoDL SSH tunnel examples show `127.0.0.1`; public custom service should be tested on a real instance before changing.
