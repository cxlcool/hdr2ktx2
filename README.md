# HDR2KTX2 v1.0

Windows desktop app built with Python, PySide6, and PyInstaller.

![hdr2ktx2项目介绍图生成](README.assets/hdr2ktx2%E9%A1%B9%E7%9B%AE%E4%BB%8B%E7%BB%8D%E5%9B%BE%E7%94%9F%E6%88%90.jpeg)





**# hdr2ktx2**

Convert the HDR file to KTX2 format that supports Cycles rendering



**# desc**

Dev Base on https://github.com/KhronosGroup/glTF-IBL-Sampler

cut compile to exe



You don't need to package and compile it!

use python3+QT to build the GUI



**# download exe to run!**





## Output format

The app runs the bundled glTF-IBL-Sampler. It turns an equirectangular HDR panorama into a GGX-prefiltered, six-face cubemap stored as KTX2 (`R16G16B16A16_SFLOAT`) with mip levels. It does not merely wrap the original panorama pixels in a KTX2 container.

## Use

1. Launch `HDR2KTX2.exe`.
2. Add `.hdr` files, choose an output directory if desired, and select sample count, cubemap size, and mip count.
3. Click **Start conversion**. By default, output files are written next to their input files. Existing outputs are skipped unless overwrite is enabled.

The bundled executable includes Python/Qt, the sampler CLI and DLLs, shaders, the Vulkan loader, and the Visual C++ runtime. A Vulkan-capable GPU and working graphics driver are still required; GPU drivers cannot be bundled with the app.

## Build

Install Python 3.11+ and the pinned packages in `requirements.txt`, then run:

```powershell
python -m pip install -r requirements.txt
.\build.ps1
```

The script writes `dist/HDR2KTX2.exe`.

The native files under `bundle/` include `cli.exe`, `GltfIblSampler.dll`, `ktx.dll`, `vulkan-1.dll`, Visual C++ runtime DLLs, and `shaders/`.

## Versioning

The displayed release version is in `version.json`. Every AI-authored change must increment that value and add a matching entry to `CHANGELOG.md`, as required by `AGENTS.md`.
