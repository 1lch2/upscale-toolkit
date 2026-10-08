# 第三方许可索引

本目录只维护许可类型和上游链接，不复制各依赖的协议全文。版本以 `requirements-lock.txt`、`requirements-torch.txt` 及发行包生成的 `runtime-versions.json` 为准。

项目包含的 Forge 派生代码采用 AGPL-3.0，版权声明与完整协议见根目录 [LICENSE](../LICENSE)，代码来源及改动见 [SOURCE_MAP.md](../SOURCE_MAP.md)。

| 组件 | 主要许可 | 上游许可或项目 |
| --- | --- | --- |
| Python | PSF-2.0 及历史许可 | [Python 许可说明](https://docs.python.org/3/license.html) |
| Tcl / Tk | Tcl/Tk 宽松许可 | [Tcl](https://github.com/tcltk/tcl/blob/main/license.terms)、[Tk](https://github.com/tcltk/tk/blob/main/license.terms) |
| PyTorch | BSD-3-Clause 及捆绑组件许可 | [PyTorch LICENSE](https://github.com/pytorch/pytorch/blob/main/LICENSE) |
| torchvision | BSD-3-Clause | [torchvision LICENSE](https://github.com/pytorch/vision/blob/main/LICENSE) |
| Spandrel | MIT；内含架构分别许可 | [Spandrel v0.4.2](https://github.com/chaiNNer-org/spandrel/tree/724cca389f28c38e1050689d4862a452fd644484) |
| DAT / SCUNet 实现 | Apache-2.0 | [DAT](https://github.com/chaiNNer-org/spandrel/blob/724cca389f28c38e1050689d4862a452fd644484/libs/spandrel/spandrel/architectures/DAT/__arch/LICENSE)、[SCUNet](https://github.com/chaiNNer-org/spandrel/blob/724cca389f28c38e1050689d4862a452fd644484/libs/spandrel/spandrel/architectures/SCUNet/__arch/LICENSE) |
| NumPy | BSD-3-Clause 及捆绑组件许可 | [NumPy LICENSE](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| Pillow | MIT-CMU 及捆绑组件许可 | [Pillow LICENSE](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| piexif | MIT | [piexif LICENSE](https://github.com/hMatoba/Piexif/blob/master/LICENSE.txt) |
| einops | MIT | [einops LICENSE](https://github.com/arogozhnikov/einops/blob/main/LICENSE) |
| safetensors | Apache-2.0 | [safetensors LICENSE](https://github.com/huggingface/safetensors/blob/main/LICENSE) |
| filelock | MIT | [filelock LICENSE](https://github.com/tox-dev/filelock/blob/main/LICENSE) |
| fsspec | BSD-3-Clause | [fsspec LICENSE](https://github.com/fsspec/filesystem_spec/blob/master/LICENSE) |
| Jinja2 / MarkupSafe | BSD-3-Clause | [Jinja2](https://github.com/pallets/jinja/blob/main/LICENSE.txt)、[MarkupSafe](https://github.com/pallets/markupsafe/blob/main/LICENSE.txt) |
| mpmath | BSD-3-Clause | [mpmath LICENSE](https://github.com/mpmath/mpmath/blob/master/LICENSE) |
| NetworkX | BSD-3-Clause | [NetworkX LICENSE](https://github.com/networkx/networkx/blob/main/LICENSE.txt) |
| packaging | Apache-2.0 OR BSD-2-Clause | [packaging LICENSE](https://github.com/pypa/packaging/blob/main/LICENSE) |
| SymPy | BSD-3-Clause | [SymPy LICENSE](https://github.com/sympy/sympy/blob/master/LICENSE) |
| typing-extensions | PSF-2.0 | [typing-extensions LICENSE](https://github.com/python/typing_extensions/blob/main/LICENSE) |
| setuptools | MIT 及内置依赖许可 | [setuptools LICENSE](https://github.com/pypa/setuptools/blob/main/LICENSE) |
| PyInstaller | GPL-2.0-or-later，含打包例外 | [PyInstaller 许可说明](https://pyinstaller.org/en/stable/license.html) |
| pyinstaller-hooks-contrib | GPL-2.0-or-later；运行时 hooks 为 Apache-2.0 | [hooks 许可说明](https://github.com/pyinstaller/pyinstaller-hooks-contrib/blob/master/LICENSE) |
| altgraph / pefile | MIT | [altgraph](https://github.com/ronaldoussoren/altgraph)、[pefile](https://github.com/erocarrera/pefile) |
| pywin32-ctypes | BSD-3-Clause | [pywin32-ctypes](https://github.com/enthought/pywin32-ctypes) |
| CUDA 运行库（仅 cu130 包） | NVIDIA 对应组件许可 | [CUDA Toolkit 许可](https://docs.nvidia.com/cuda/eula/index.html)及 Torch wheel 内的随附声明 |

表中是组件的主要许可，不能替代具体版本的完整声明；Torch、NumPy、Pillow、Spandrel 等还包含各自许可的第三方代码。模型实现的许可也不代表 UltraSharp V2 或 ScuNET 权重的再分发许可。

## 构建时收集

`tools/collect_licenses.py` 从构建环境收集依赖随附的 LICENSE、COPYING、NOTICE 等文件和 Python/Tk 许可；Spandrel wheel 缺少的架构许可从固定提交的源码包补齐，并检查 SHA-256。缺失的 Tcl 许可按实际 Tcl 补丁版本从上游取得。下载缓存放在 `.cache/license-downloads`，首次构建需要访问 GitHub；下载或校验失败会中止构建。

收集结果仅写入 `build` 并随 EXE 发行，不提交回本目录。产物中的 `licenses/sources.json` 记录补充来源。升级 Spandrel 时需同步更新收集脚本中的版本、提交和源码包校验值。

发行包仍保留所需的协议原文与版权声明：[MIT](https://opensource.org/license/mit) 要求随副本保留版权及许可声明，[Apache-2.0 第 4 节](https://www.apache.org/licenses/LICENSE-2.0) 要求提供许可证副本并在适用时保留 NOTICE。仓库的链接索引用于阅读和维护，不作为发行包随附声明的替代。
