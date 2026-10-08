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

发行版本由 Git tag 决定，采用可带 `v` 前缀的语义化版本，例如 `v1.2.3` 或 `v1.3.0-rc.1`。构建生成 `upscale_toolkit/_version.py`，由应用与打包工具共同读取；该文件加入源码交付包，但被 Git 忽略。无需手动修改 `__version__`。本地可使用 `build.ps1 -Tag v1.2.3`；未提供 tag 时沿用已有生成版本，没有生成版本则使用开发版本 `0.0.0.dev0`。

工作流只响应 tag push，不响应分支 push、PR 或手动运行。推送版本 tag 后构建 CPU 与 cu130，两者成功才发布该 tag 对应的 Release；预发布版本标为 Pre-release。发布附件包含 ZIP、SHA-256 和分别命名的构建记录。上传失败留下草稿，重跑会补齐附件后发布；已发布的 tag 直接跳过。仅发布任务拥有 `contents: write` 权限，使用内置 `GITHUB_TOKEN`。自动发布不代表真实模型质量和 GPU 路径已通过验收，这两项需另行验证。

GitHub 托管 Windows runner 上的 CUDA 包也使用 CPU 推理验收；它只证明 CUDA 运行库打包后的 CPU 路径可用，不证明 GPU 路径通过。测试输出在 `artifacts`，打包版本/依赖/模型策略记录在 `build/<runtime>/metadata` 及发行目录。

依赖许可类型与链接集中在 `licenses/README.md`。许可正文由构建自动收集，首次构建需联网获取缺失的上游声明，后续使用 `.cache/license-downloads`。不要将生成的许可目录提交回仓库；升级依赖时同步检查索引，升级 Spandrel 时还需更新收集脚本中的固定来源与校验值。
