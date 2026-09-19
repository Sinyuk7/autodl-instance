# AutoDL Next Session Plan

Updated: 2026-09-19

## Restart context

The instance is being restarted so AutoDL can mount file storage at
`/root/autodl-fs`. The source checkout is `/root/autodl-instance`; a normal
restart should retain both the system disk and `/root/autodl-tmp` data disk.

Do not run `autodl setup`, `autodl start`, or migrate/delete files immediately
after restart. Re-audit mounts and review the working tree first.

## Verified pre-restart state

- `/root/autodl-tmp` is an independent 50G XFS data-disk mount.
- `/root/autodl-fs` did not exist before restart.
- `/root/ComfyUI` is detached at tag `v0.36.0` and has no dedicated venv.
- ComfyUI `user`, `output`, and `models` are physical system-disk directories.
- `/root/autodl-tmp/models` does not exist.
- One 13.79GB model is stored directly under `/root/autodl-tmp`.
- Mihomo 1.19.20 was running on loopback ports 7890 and 9090 using the private
  config under `/root/autodl-tmp/comfyui-workspace/mihomo/`.
- The instance was in no-GPU mode with a 0.5 CPU and 2GiB memory cgroup limit.
- No backup archive was found in the inspected data-disk paths.

Never print Mihomo configuration, subscription URLs, tokens, secrets, or SSH
private keys.

## Code work completed before restart

- Restored `src/addons/torch_engine/plugin.py` so lifecycle imports resolve.
- Removed automatic process-name cleanup from the lifecycle entry point.
- Replaced unconditional `fuser -k -9 6006/tcp` behavior:
  - start refuses an occupied port without killing anything;
  - stop sends SIGTERM only when listener cwd and command line prove ownership.
- Added focused tests for lifecycle import and process ownership behavior.

The working tree may contain these uncommitted changes. Preserve and inspect
them with `git status` and `git diff`; do not reset them.

## First actions after restart

1. Verify `/root`, `/root/autodl-tmp`, and `/root/autodl-fs` independently with
   `findmnt -T`, `mountpoint`, `df -hT`, and `df -i`.
2. Confirm Git status and review the pre-restart code diff.
3. Confirm Mihomo process/listeners. Do not assume it survived restart and do
   not inject global proxy variables.
4. Inspect `/root/autodl-fs` capacity and permissions without writing data.
5. Run the focused unit tests only if pytest is already available; do not let a
   test command auto-install dependencies.

## Next implementation order

1. Create `/root/autodl-tmp/comfyui-workspace/user` and `output`, migrate with
   conflict preservation, then link `/root/ComfyUI/user` and `output`.
2. Identify the orphan model type, create `/root/autodl-tmp/models/<type>`,
   migrate it, and link `/root/ComfyUI/models`.
3. Review and repair `autodl init` and `autodl setup`; proxy startup must use
   absolute paths under the configured `workspace_data_dir/mihomo` directory.
4. Create a dedicated ComfyUI Python environment on the system disk only after
   checking free space. Avoid duplicating CUDA/Torch packages until the target
   environment and GPU mode are confirmed.
5. Switch to a GPU-enabled instance and validate NVIDIA devices, Torch CUDA,
   local `0.0.0.0:6006`, and the AutoDL public port mapping separately.

## Explicitly deferred

- No migration, symlink creation, package installation, or environment creation
  was performed before restart.
- No setup/start/stop lifecycle command was run.
- No commit or push was performed.
