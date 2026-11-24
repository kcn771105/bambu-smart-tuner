# 上传到 GitHub（照着敲就行）

仓库已经在本机准备好了：`.git` 已初始化、分支是 `main`、首次提交已完成、体积 1.8 MB。
剩下只有三步：**建远程仓库 → 关联 → 推送**，然后可选地发一个 Release 挂 EXE。

---

## 0. 先确认本机状态（可选）

```powershell
cd "F:\deep seek\bambu_smart_tuner"
git log --oneline          # 应该看到 1 条提交
git status -s              # 应该是空的
```

---

## 1. 在 GitHub 上建一个空仓库

1. 打开 https://github.com/new
2. **Repository name**：`bambu-smart-tuner`
3. **Description**（可填）：`Bambu Studio 3mf 智能调参工具（PySide6，只改工艺页参数）`
4. 选 **Public**（想私有就选 Private，功能一样）
5. **不要**勾 `Add a README file`、`Add .gitignore`、`Choose a license`
   —— 本地已经有 README 和 .gitignore，勾了会冲突
6. 点 **Create repository**，把页面上那串地址复制下来，形如
   `https://github.com/<你的用户名>/bambu-smart-tuner.git`

---

## 2. 关联远程并推送

```powershell
cd "F:\deep seek\bambu_smart_tuner"
git remote add origin https://github.com/<你的用户名>/bambu-smart-tuner.git
git push -u origin main
```

推送时会弹窗要账号密码：

- **用户名**：你的 GitHub 用户名
- **密码**：**不能用登录密码**，必须用 Personal Access Token（下面第 3 步）

> 如果弹的是「Sign in with your browser」，点它也行，浏览器授权后自动完成。

---

## 3. 生成 Personal Access Token（只做一次）

1. 打开 https://github.com/settings/tokens
2. **Fine-grained tokens** → **Generate new token**
3. Name 随便写（如 `bambu-tuner-push`）
4. Expiration 选 90 天或自定义
5. **Repository access** → `Only select repositories` → 选刚建的 `bambu-smart-tuner`
6. **Permissions** → `Repository permissions` → **Contents: Read and write**
   （只需要这一项）
7. 生成后立刻复制（形如 `github_pat_xxxxx`，只显示一次）
8. 回到终端，密码处粘贴这个 token

想省事也可以让 git 记住它（Windows 凭据管理器会存）：

```powershell
git config --global credential.helper manager
```

以后就不用再输了。

---

## 4. 发一个 Release，把 EXE 挂上去

仓库里**不放** exe/zip（`.gitignore` 已经把 `dist/`、`build/`、`release/` 排除了，
这仨加起来 180 MB，放仓库里 clone 会很难受）。二进制走 Release：

### 网页操作

1. 仓库页右侧 **Releases** → **Create a new release**
2. **Choose a tag** → 输入 `v1.0` → **Create new tag on publish**
3. **Release title**：`v1.0 — 首个可用版本`
4. **Describe this release**（可复制）：

   ```
   支持机型：X1 / X1C / X1E / P1P / P1S / P2S / P2P / A1 / A1 mini / H2D / H2D Pro / H2S
   支持耗材：PLA / PETG / ABS / ASA / TPU
   六档模式：强度优先 / 表面质量优先 / 均衡 / 快速草稿 / 精细 / 超精细

   下载 BambuSmartTuner-v1.0-win64.zip，解压后双击 BambuSmartTuner.exe。
   Windows 10/11 x64，无需安装 Python。
   ```

5. 把 `F:\deep seek\bambu_smart_tuner\release\BambuSmartTuner-v1.0-win64.zip`（44 MB）拖进
   **Attach binaries** 区域
6. **Publish release**

### 命令行操作（要先装 gh）

```powershell
winget install --id GitHub.cli
gh auth login                     # 选 GitHub.com → HTTPS → 浏览器登录
cd "F:\deep seek\bambu_smart_tuner"
gh release create v1.0 "release\BambuSmartTuner-v1.0-win64.zip" `
  --title "v1.0 — 首个可用版本" `
  --notes "Windows 10/11 x64，解压即用，无需安装 Python。"
```

---

## 5. 以后改代码怎么更新

```powershell
cd "F:\deep seek\bambu_smart_tuner"
git add -A
git commit -m "说明这次改了什么"
git push
```

---

## 6. 已经替你处理好的坑

| 坑 | 处理 |
| --- | --- |
| `dist/ build/ release/` 共 180 MB 会把仓库撑爆 | 已写进 `.gitignore`，实际提交只有 **2.9 MB / 280 个文件** |
| `rules/BambuRules.json.bak*` 有 18 个历史备份 | `.gitignore` 里 `*.bak*` 全排除，只留正式那份 |
| `__pycache__`、`.pytest_cache`、`*.log` | 已排除 |
| 中文文件名在 `git status` 里显示成 `\344\270\255` | 已设 `git config core.quotepath false` |
| Windows 换行警告 `LF will be replaced by CRLF` | 已设 `core.autocrlf true`，警告可以无视 |
| 提交身份没配会报 `Please tell me who you are` | 已在仓库内设好（`bambu-smart-tuner` / noreply 邮箱），想换成自己的：`git config user.name "你的名字"` + `git config user.email "你的邮箱"` |

---

## 7. 常见报错对照

| 报错 | 原因与解法 |
| --- | --- |
| `remote: Support for password authentication was removed` | 用了登录密码而不是 token，回到第 3 步 |
| `remote: Permission to xxx denied to yyy` | token 没有这个仓库的 Contents 写权限，或者账号不对 |
| `error: remote origin already exists` | 先 `git remote remove origin` 再重新 add |
| `src refspec main does not match any` | 本地还没有提交，`git log` 确认有提交；分支名用 `git branch --show-current` 看 |
| `Failed to connect to github.com port 443` | 网络问题，重试；或改用 SSH：`git remote set-url origin git@github.com:<用户名>/<仓库>.git` |
| 推上去以后看不到 exe | 正常，exe 在 Release 里，不在源码树里（第 4 步） |
| 想加开源协议 | 网页仓库页 **Add file → Create new file**，文件名 `LICENSE`，GitHub 会提示选模板（MIT 最常用） |

---

## 8. 建议顺手做的两件事

1. **加 LICENSE**：没有协议别人不敢用。MIT 最省事。
2. **仓库 About 里填 Topics**：`bambu-lab` `bambu-studio` `3d-printing` `pyside6` `slicer`，
   别人搜得到。
