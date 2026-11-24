# 上传到 GitHub

本机已经准备好：`.git` 已初始化、分支 `main`、**4 条提交**、**114 个文件 / 2.6 MB**、工作区干净。
所以不需要再 `git init`，也不需要重新整理文件，只剩「推到 GitHub」这一步。

三种方法，按省事程度排，选一种就行。

---

## 方法一：GitHub Desktop（推荐，点三下）

### 1. 装软件

https://desktop.github.com → **Download for Windows** → 安装 → 打开。

### 2. 登录

首次打开点 `Sign in to GitHub.com` → 浏览器弹出后点 **Authorize desktop** → 回到软件看到头像即成功。
若问 Name / Email，填 GitHub 用户名和邮箱（只影响以后提交显示的作者）。

### 3. 加入现有仓库

菜单 **File → Add local repository…**

- **Local path** → `Choose…` → 选到
  ```
  F:\deep seek\bambu_smart_tuner
  ```
  选**这个文件夹本身**，不要选里面的 `core`、`ui` 等子目录。
- 点 **Add repository**

左侧 Current Repository 出现 `bambu_smart_tuner`，中间 History 能看到 4 条提交即正确。

### 4. 发布（这一步才是上传）

右上角 **Publish repository** → 弹窗：

| 字段 | 填什么 |
| --- | --- |
| Name | `bambu-smart-tuner` |
| Description | 见文末「描述文案」第一节 |
| **Keep this code private** | **去掉勾**（要公开） |

点 **Publish repository**，等进度条走完（2.6 MB，几秒到半分钟）。
浏览器打开 `https://github.com/<你的用户名>/bambu-smart-tuner` 即可看到。

### 5. 以后更新

左下角填一句说明 → **Commit to main** → 右上角 **Push origin**。

---

## 方法二：网页拖拽（不装软件）

### 1. 建空仓库

https://github.com/new

- **Repository name**：`bambu-smart-tuner`
- 选 **Public**
- **三个勾全部不要勾**（Add a README / .gitignore / license）——本地都有，勾了会冲突
- **Create repository**

### 2. 进入上传页

建完跳到仓库页，**Quick setup** 区域右上角有链接 `uploading an existing file`，
点它，或直接访问 `https://github.com/<你的用户名>/bambu-smart-tuner/upload`。

### 3. 拖文件

资源管理器打开：

```
F:\deep seek\bambu_smart_tuner\_upload_github
```

这个目录里就是筛好的 **19 项 / 114 个文件**（10 个文件夹 + 9 个根文件 + 上传清单.txt）。

- **Ctrl+A 全选**，用鼠标全部拖到浏览器虚线框里
- 只拖这个目录**里面的内容**，不要把这个目录本身拖进去（否则多一层）
- 单次上限 100 个文件：报错就分两批，先拖 10 个文件夹，提交后再拖 9 个文件
- `上传清单.txt` 可不传（只是给你看的说明）

### 4. 提交

页面下方 **Commit changes** 填 `Bambu Smart Tuner v1.0` → **Commit changes**。

> 网页上传**不读 `.gitignore`**，所以务必只拖 `_upload_github` 里的东西。
> 直接从工程根目录拖会把 `dist / build / release`（共 180 MB）也带上，必然失败。

---

## 方法三：命令行（本机已配好）

```powershell
cd "F:\deep seek\bambu_smart_tuner"
git remote add origin https://github.com/<你的用户名>/bambu-smart-tuner.git
git push -u origin main
```

要密码时粘 **Personal Access Token**：
https://github.com/settings/tokens → **Fine-grained tokens** → Generate new token
→ Repository access 选 `Only select repositories` → 勾目标仓库
→ Permissions → Repository permissions → **Contents: Read and write**

想让它记住密码：

```powershell
git config --global credential.helper manager
```

---

## 发 Release（三种方法之后都做，exe 走这里）

仓库**不放** exe/zip（`dist / build / release` 共 180 MB，已被 `.gitignore` 排除）。
二进制走 Release：

1. 仓库页右侧 **Releases** → **Create a new release**
2. **Choose a tag** 输入 `v1.0` → 点 `Create new tag on publish`
3. **Release title**：`v1.0 — 首个可用版本`
4. **Describe this release**：粘文末「描述文案」第三节
5. **Attach binaries** 区域拖入
   ```
   F:\deep seek\bambu_smart_tuner\release\BambuSmartTuner-v1.0-win64.zip
   ```
   （44 MB，等它显示成一条带文件名的记录才算传完）
6. **Publish release**

---

## 描述文案（直接复制）

### 一、仓库 Description（About 那一行）

**推荐**
```
拓竹 3D 打印机独立调参工具：读 Bambu Studio 的 3mf，按机型+耗材+喷嘴+模式+模型几何自动优化全套切片工艺参数，另存新 3mf。只改工艺页，不动机器/耗材设置。
```

**短版**
```
Bambu Studio 3mf 智能调参工具 · 13 机型 × 5 耗材 × 6 模式 · 只写切片工艺页
```

**带英文（利于搜索）**
```
Bambu Lab 3mf smart tuning tool — auto-optimizes slicer process settings by printer, filament, nozzle, mode and model geometry. Process page only. Windows GUI, PySide6.
```

### 二、Topics（About 右侧齿轮里填）

```
bambu-lab
bambu-studio
3d-printing
pyside6
slicer
python
windows
desktop-app
```

### 三、Release 说明

**Title**
```
v1.0 — 首个可用版本
```

**正文**

```markdown
Windows 10/11 x64 免安装版。下载 `BambuSmartTuner-v1.0-win64.zip`，解压后双击 `BambuSmartTuner.exe`，不需要 Python。

## 它做什么

读 Bambu Studio 保存的 `.3mf` 工程 → 自动识别机型/耗材/喷嘴/热端流量类型/打印板/真机上限 → 按你选的模式算出一整套切片工艺参数（365 项）→ 对比表给你看每项为什么改 → 另存新 3mf，回 Studio 直接切片。

**只改「切片工艺」页。** 机器页（硬件上限/喷嘴/板面）和耗材页（温度/冷却/回抽/流量/AMS）只读取来约束工艺参数，一个字符都不写回。

## 支持范围

- **机型 13 个**：X1 / X1C / X1E / P1P / P1S / P2S / P2P / A1 / A1 mini / H2D / H2D Pro / H2S / 通用保守
- **耗材 5 种**：PLA / PETG / ABS / ASA / TPU（也可同步 Bambu 自定义耗材）
- **喷嘴 4 档**：0.2 / 0.4 / 0.6 / 0.8 mm，换喷嘴会同步重算体积流量上限
- **热端 3 类**：标准流量 / 高流量 / E3D 高流量
- **打印板 6 种**：Supertack / 纹理 PEI / 光面 PEI / 高温板 / 工程板 / 低温板
- **六档模式**：强度优先 / 表面质量优先 / 均衡 / 快速草稿 / 精细 / 超精细

## 按模型调，不是套模板

逐件实测壁厚、细高比、悬垂面积、顶盖占比、最薄特征，然后推导墙圈数、层高上限、首层速度、顶底壳层、接缝位置、裙边宽度（倾覆指数）、支撑密度与形态。每条结论都能看到实测值、公式和结论三列。

## 其它

- 叠乘总闸：同一参数被多层连乘时限制在 ×0.6~×1.8，避免「越优化越慢」
- 时长预算：按档位给定涨幅上限（均衡 40%、草稿 10%、强度 200%、质量 170%）
- 写入自检：存完自动重开文件逐项比对，并检查 `different_settings_to_system` 是否声明（不声明 Studio 会用预设盖掉你的值）
- 预设隔离：只写这一个工程文件，从不写 Bambu Studio 的耗材/工艺/机型预设

## 已知限制

- 逐件不同参数要在 Bambu Studio 里手动调（切片参数本质是整盘全局的，本程序按最保守的一件合并）
- 时长是相对估算，误差 20~40%，以 Studio 切完的实际时间为准
- 首次启动 3~8 秒（单文件 EXE 自解压）
- 未签名，部分杀软会误报，加白即可

详细文档见仓库 `README.md`。
```

---

## 本机已替你处理好的坑

| 坑 | 处理 |
| --- | --- |
| `dist/ build/ release/` 共 180 MB 会把仓库撑爆 | `.gitignore` 已排除，实际提交 **114 个文件 / 2.6 MB** |
| `rules/BambuRules.json.bak*` 有 18 个历史备份 | `*.bak*` 全排除 |
| `tools/_pNN.py` 167 个一次性补丁脚本 | 已从仓库剔除并加进 `.gitignore`，只留 36 个正式工具 |
| `__pycache__`、`.pytest_cache`、`*.log` | 已排除 |
| 中文名在 `git status` 显示成 `\344\270\255` | 已设 `core.quotepath false` |
| Windows 换行警告 `LF will be replaced by CRLF` | 已设 `core.autocrlf true`，警告可无视 |
| 提交身份 | 仓库内已设 `bambu-smart-tuner` / noreply 邮箱；改成自己的：`git config user.name "名字"` + `git config user.email "邮箱"` |

---

## 常见报错对照

| 报错 / 现象 | 原因与解法 |
| --- | --- |
| `Support for password authentication was removed` | 用了登录密码，改用 Token |
| `Permission to xxx denied to yyy` | Token 少了 Contents 写权限，或账号不对 |
| `remote origin already exists` | `git remote remove origin` 后重新 add |
| `src refspec main does not match any` | 本地没有提交；`git log --oneline` 确认，`git branch --show-current` 看分支名 |
| `Failed to connect to github.com port 443` | 网络问题；可换 SSH：`git remote set-url origin git@github.com:<用户名>/bambu-smart-tuner.git` |
| GitHub Desktop 提示「不是 Git 仓库」 | 路径选成了子目录，重选 `F:\deep seek\bambu_smart_tuner` |
| 网页拖拽后目录被拍平、没有 core/ui | 拖的是文件夹「里面」的内容，或浏览器不支持目录拖拽 → 改用方法一 |
| 推上去看不到 exe | 正常，exe 在 Release 里 |
| Release 附件一直 loading | 44 MB 上传慢，等 1~2 分钟；网络差就重试 |

---

## 收尾建议

1. **加 LICENSE**：网页仓库页 → Add file → Create new file → 文件名 `LICENSE` → GitHub 会给模板，MIT 最省事。
2. **About 里填 Topics**（见上文第二节），否则别人搜不到。
3. 把 Release 链接贴到 README 顶部，用户点一下就能下 exe。
