# Release Checklist — autodl-instance

## 版本规则

| 事项 | 规则 |
|------|------|
| 版本号 | `pyproject.toml` `[project] version` 单一来源 |
| bump | `bump2version` 或手动改 `version` 字段 |
| tag | `git tag v$(hatch version)` |
| rollback | `git revert <tag>` + 重打 patch version |

## 构建验证

```bash
# 1. 清理旧产物
rm -rf dist/

# 2. 构建 wheel
hatch build

# 3. 本地 smoke（当前环境）
pip install dist/autodl_instance-*.whl --force-reinstall --no-deps
autodl --help
autodl status 2>/dev/null || true
autodl doctor 2>/dev/null || true

# 4. 卸载
pip uninstall autodl-instance -y
```

## 真实 AutoDL Smoke

在新 AutoDL 实例上执行：

```bash
# 1. 安装（三选一）
uv tool install autodl-instance                         # PyPI
uv tool install dist/autodl_instance-0.1.0-py3-none-any.whl  # 本地 wheel
uv tool install https://github.com/<org>/autodl-instance/releases/download/v0.1.0/autodl_instance-0.1.0-py3-none-any.whl  # GitHub Release

# 2. 配置
autodl init --base-dir /root/autodl-tmp --userdata-repo <repo-url>

# 3. 设置 secrets
autodl secrets set HF_TOKEN
autodl secrets set CIVITAI_API_TOKEN

# 4. 执行 setup
autodl setup

# 5. 验证
autodl status
autodl doctor

# 6. 收尾
autodl bye
```

## GitHub Release 发布路径

```bash
# 1. bump 版本
# 编辑 pyproject.toml version

# 2. 构建
hatch build

# 3. 创建 tag
git tag v$(hatch version)
git push origin v$(hatch version)

# 4. 创建 Release（手动或 gh CLI）
gh release create v$(hatch version) dist/*.whl --title "v$(hatch version)" --notes "Release notes"
```

## PyPI 发布路径

```bash
hatch build
hatch publish
```

## 回滚

```bash
# 撤销 Release
gh release delete v0.1.0 --yes
git tag -d v0.1.0
git push origin :refs/tags/v0.1.0

# 撤销 PyPI（不可逆，只能 yank）
# 通过 PyPI web UI 操作
```

## 发布前检查清单

- [ ] `hatch build` 通过
- [ ] 本地 wheel smoke 通过
- [ ] AutoDL 实例 smoke 通过
- [ ] `autodl setup` 幂等（重复执行不报错）
- [ ] `autodl status` 输出健康
- [ ] `autodl doctor` 诊断通过
- [ ] `autodl bye` 正常退出
- [ ] `version` 已 bump
- [ ] `git tag` 已打
- [ ] CHANGELOG 已更新（如适用）
