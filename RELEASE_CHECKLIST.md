# 更新检查

1. 确认 Git 工作区和目标变更，保留用户数据。
2. 运行 pytest tests/ -q 和 git diff --check。
3. 同步 README、配置默认值和命令帮助。
4. 使用 uv tool install --editable --force /root/autodl-instance 安装。
5. 从 /tmp 验证 autodl --help 和 autodl model --help，确认导入来源为工作树。
6. 修改依赖或入口后重新安装；普通 Python 修改立即生效。

真实 setup、模型下载和 GPU 推理单独验证并报告，不能以 Mock 测试替代。
commit/push 或发布需要用户明确要求。
