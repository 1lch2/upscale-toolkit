# Upscale Toolkit

独立 Windows 图像放大与去噪桌面应用，从 Forge 抽取并复用图像处理逻辑。

## 使用

打开 `UpscaleToolkit.exe`，选择单张图片或目录，指定处理模式、输出大小和输出目录，点击“开始处理”。目录模式可递归处理并保留相对目录结构。已有文件自动加后缀，不覆盖源图。

- **放大**：UltraSharp V2（DAT，原生 4×）。默认输出 4 倍，可指定任意正倍率、最大边或目标宽高。
- **去噪**：ScuNET（SCUNet，原生 1×）。默认保持原尺寸，可主动开启普通尺寸调整。
- **放大与去噪融合**：同一原图分别经过两个模型，统一到目标尺寸后融合。滑块表示 ScuNET 结果占比；ScuNET 分支的尺寸调整使用 Lanczos。

按宽高可锁定比例，或选择保持比例放入、填满后居中裁剪。PNG / WebP 保留透明区域；JPEG 可选择白色或黑色背景。保留源图的 SD 生成参数并追加本次处理信息；不承诺完整保留相机 EXIF。暂不支持高位深、CMYK 或动画/多帧图像。

高级设置默认自动选择 CUDA，否则使用 CPU。默认 FP32；CUDA 可开启半精度（DAT 使用 BF16，SCUNet 使用 FP16）。分块默认 256、重叠 16，0 表示整图。减小分块通常能降低 GPU 推理内存。推理与目录队列串行执行。取消在当前分块推理结束后生效，已完成的文件保留，未完成任务不保存。

整个文件夹为交付单位，可移动目录。公开构建不附带预训练权重，请自行取得以下两份模型，放到 EXE 同目录的 `model`，保留文件名：

```text
UpscaleToolkit.exe
model/4x-UltraSharpV2.pth
model/ScuNET.pth
licenses/
source/
```

无需 Forge 或预装 Python。CUDA 需要支持的 NVIDIA 显卡及驱动；可在高级设置选择 CPU。配置、日志和最近任务报告位于 `%LOCALAPPDATA%\UpscaleToolkit`，界面“详情”可查看任务错误。

## 开发与构建

Windows x64、Python 3.13、Tkinter/ttk、Torch 和 Spandrel。新开发者可以从公开依赖源建立环境，无需 Forge。CPU 和 CUDA 使用相同代码，Torch 从对应的官方 wheel 源安装，公共依赖锁定在 `requirements-lock.txt`，Torch 版本锁定在 `requirements-torch.txt`。

```powershell
pwsh -NoProfile -File ./tools/setup_environment.ps1 -Runtime cu130
& ./.venv/Scripts/python.exe app.py
pwsh -NoProfile -File ./build.ps1 -Runtime cu130 -Release
```

`setup_environment.ps1 -Runtime cpu` 创建 CPU 环境；更换运行库时建议使用不同 venv，例如 `-Venv .ci-venv`。`build.ps1 -Python <解释器>` 可指定已有构建环境。构建入口核对安装的 Torch 与所选运行库，收集实际依赖版本和许可证，然后执行 PyInstaller。构建缓存放在项目 `.cache/pyinstaller/<runtime>`，每次构建清理 PyInstaller 缓存，避免重复构建沿用旧代码。

输出为 `dist/<runtime>/UpscaleToolkit/`，`-Release` 额外生成 `UpscaleToolkit-<版本>-windows-x64-<runtime>.zip`、SHA-256 和 `release.json`。版本只维护 `upscale_toolkit/__init__.py` 的 `__version__`。公开包默认只有模型目录说明；需要包含已准备好的权重时，显式添加 `-IncludeModels`。

无需 GPU 或真实权重的完整 CI 验收：

```powershell
& ./.venv/Scripts/python.exe -B ./tools/create_ci_models.py --output ./build/ci-models
pwsh -NoProfile -File ./build.ps1 -Runtime cpu -Release -Verify -TestModelDir ./build/ci-models
```

该示例需 CPU 环境；CUDA 构建环境可将命令的 `-Runtime` 改为 `cu130`，仍以 CPU 推理执行托管 CI 验收。临时权重是未训练的微型架构，仅验证加载/处理链路，不代表真实模型质量，也不会进入发行包。真实模型验证使用 `tools/e2e.py --device cuda`，需要相应权重和硬件。

应用还支持 CLI `--input <图片或目录> --output <目录> --mode upscale|denoise|blend --report <JSON>`，以及 `--device cpu|cuda|auto`、`--scale`、`--width/--height`、`--crop`、`--blend`、`--recursive`、`--half`、`--tile`、`--overlap`、`--format png|jpg|webp`。无 CLI 参数即打开桌面窗口。

## GitHub Actions

[ci.yml](.github/workflows/ci.yml) 在 PR 和普通 push 上安装 CPU 环境，执行完整构建/验收并上传 ZIP、校验文件及诊断报告。`v*` 标签构建 CPU 与 cu130 两种包，并检查标签与应用版本一致；手动运行可选择其中一种或两种。公开工作流不使用私有模型、Forge、secrets 或有写权限的仓库 token，不自动发布 GitHub Release。

实际 GPU 推理需在支持的显卡/驱动上另行验收。开发流程及验证边界见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 来源与许可证

随包源码位于 `source`，包含对应代码、构建脚本、依赖锁定文件与工作流。在该目录准备独立 `.venv` 后可执行相同的 `build.ps1`；必要时使用交付根目录的 `model`。源码直接运行时需在源码目录准备 `model`。

Forge 抽取代码为 AGPL-3.0，来源及必要改动见 `SOURCE_MAP.md` 和 `source-manifest.json`，完整协议保留在根目录 `LICENSE`。仓库的 [依赖许可索引](licenses/README.md) 仅列出许可类型与上游链接；发行包所需的完整许可和版权声明由构建脚本自动收集到 `build/<runtime>/metadata/licenses`，再随发行包交付。首次构建会联网补齐 Spandrel 和缺失的 Tcl 许可，后续复用 `.cache/license-downloads`。模型权重由使用者自行准备，其许可与应用源码许可独立；分发包含权重的构建前，需确认相应模型允许再分发。

构建的运行库、版本和模型策略见产物 `build-manifest.json`，实际依赖版本记录于构建生成的 `runtime-versions.json`，测试报告位于 `artifacts`。`tools/extract_forge.py` 用于从指定 Forge 源码目录重新抽取原函数，不属于日常构建流程，执行时会覆盖已适配代码。
