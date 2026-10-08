# 开发与验证

Windows x64，Python 3.13。日常 CI 使用 CPU 环境，不要求 Forge、CUDA 或预训练权重：

```powershell
pwsh -NoProfile -File ./tools/setup_environment.ps1 -Runtime cpu
& ./.venv/Scripts/python.exe -B ./tools/create_ci_models.py --output ./build/ci-models
pwsh -NoProfile -File ./build.ps1 -Runtime cpu -Release -Verify -TestModelDir ./build/ci-models
```

此命令执行源码 E2E、PyInstaller 构建、EXE E2E、真实 Tk 操作验收、ZIP 打包及解压后独立运行验收。测试权重是现场生成的未训练微型 DAT/SCUNet，仅证明加载和处理流程，不证明 UltraSharp V2 / ScuNET 的实际图像质量。测试权重不进入发行包。

默认发行包不包含权重，保留 `model/README.md`。预训练模型使用和公众再分发条件需单独确认；不要将模型权重提交到 Git。原始 Forge 函数及版权/许可记录见 `SOURCE_MAP.md`、`source-manifest.json` 和 `LICENSE`，修改抽取核心时同步记录必要行为差异。

真实模型与 CUDA 验证在有相应权重和显卡的开发机器运行：

```powershell
& ./.venv/Scripts/python.exe -B ./tools/e2e.py --device cuda --name local-cuda
```

该命令需要 CUDA 构建环境与项目 `model` 内的真实权重。`core_acceptance.py` 是依赖 Forge 源码和 tqdm 的原函数参考验收，属于迁移/核心改动验证，不纳入独立的公开 CI。

版本号只维护 `upscale_toolkit/__init__.py` 的 `__version__`。`v*` 标签必须与其一致，工作流会检查并构建 CPU 与 cu130 两种产物。PR/普通 push 只构建 CPU；手动 workflow 可选择 CPU、cu130 或两者。工作流上传 Actions artifacts，不创建或发布 GitHub Release。正式发版前，应另外完成真实模型的质量和对应 GPU 运行验收。

GitHub 托管 Windows runner 上的 CUDA 包也使用 CPU 推理验收；它只证明 CUDA 运行库打包后的 CPU 路径可用，不证明 GPU 路径通过。测试输出在 `artifacts`，打包版本/依赖/模型策略记录在 `build/<runtime>/metadata` 及发行目录。

依赖许可类型与链接集中在 `licenses/README.md`。许可正文由构建自动收集，首次构建需联网获取缺失的上游声明，后续使用 `.cache/license-downloads`。不要将生成的许可目录提交回仓库；升级依赖时同步检查索引，升级 Spandrel 时还需更新收集脚本中的固定来源与校验值。
