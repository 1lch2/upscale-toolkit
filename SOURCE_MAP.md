# 代码抽取与必要改动

来源：Stable Diffusion WebUI Forge Classic 的图像后处理代码。
源文件 SHA-256 记录于 `source-manifest.json`。Forge 许可与版权声明保留在根目录 `LICENSE`。

| 应用文件 | Forge 原函数 / 文件 | 保留与改动 |
| --- | --- | --- |
| `forge_tensor.py` | `upscaler_utils.py::pil_image_to_torch_bgr / torch_bgr_to_pil_image` | 原函数抽取，保持 BGR 顺序、归一化和 CPU uint8 截断行为 |
| `forge_grid.py` | `images.py::Grid / split_grid / combine_grid` | 原函数抽取；小图缩小 tile、防负坐标；0 重叠改用直接拼接 |
| `engine.py::patch` | `upscaler_utils.py::upscale_pil_patch / _model` | 保留张量转换及实际 DAT 半精度默认 dtype 适配；移除 Forge devices / torch_utils |
| `engine.py::tiled` | `upscaler_utils.py::upscale_with_model_cpu` | 保留逐块推理和 CPU 网格合成；将全局 state/tqdm 改成任务事件与回调，取消抛异常 |
| `engine.py::load` | `modelloader.py::load_spandrel_model`, `backend/utils.py::load_torch_file` | 保留安全 CPU 读取、state_dict 解包、Spandrel descriptor；固定两份路径、保留 FP32 CPU 权重、仅一个活动 GPU 模型 |
| `engine.py::branch` | `upscaler.py::Upscaler.upscale`, `postprocessing_upscale.py::_upscale` | 保留最多四轮、无增长停止、最终 Lanczos 与中心 crop；去掉 8 像素对齐，支持准确的目标边界 |
| `engine.py::process` | `postprocessing_upscale.py::process` | 保留同源图双独立分支与 Image.blend；跳过 0/1 端点无贡献分支 |
| `image_io.py` | `images.py::read_info_from_image / save_image_with_geninfo`, `postprocessing.py::run_postprocessing` | 保留标准 parameters / EXIF UserComment 和逐图元数据副本；去掉 Forge opts、NovelAI、隐写扩展，增加原子写出、alpha、EXIF 方向 |
| `ui.py / jobs.py / options.py / storage.py / app.py` | 桌面适配 | 新增窗口、目录清单、任务队列、精确尺寸语义、配置/日志；不包含 WebUI 启动逻辑 |

未引入 Forge 模块 import、扩散模型、Gradio、全局显存调度、模型下载和 RRDB 全局 monkey patch。两份实际权重均由 Spandrel core 支持，不需要 extra arches。

`tools/core_acceptance.py` 可对照调用者提供的 Forge 源码执行参考验收。尺寸为 8 的倍数、同参数时可直接对照；新应用精确输出的非 8 倍尺寸属于明确的产品差异。
