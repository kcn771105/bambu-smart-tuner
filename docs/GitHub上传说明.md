# 上传到 GitHub（v1.2.2）

仓库已存在：https://github.com/kcn771105/bambu-smart-tuner
本机 `.git` 已就绪（分支 `main`，remote `origin` 指向上面这个仓库）。
所以「发 GitHub」= **提交 + 推**这两步，不用再 init、不用重配 remote。

---

## 一、发之前先看清两件事

1. **代码进仓库，exe 不进仓库**。`.gitignore` 已排除 `dist/`、`build/`、`release/`、`__pycache__`；
   exe 走 **Releases 附件**（网页上传 zip），这样仓库不会变成 45 MB 的大包。
2. **`_upload_github/` 是历史遗留的一份快照**，同样被 ignore。现在有 git 了就不用再管它。

---

## 二、三步发上去

### 1. 提交这一版

```powershell
cd "F:\deep seekambu_smart_tuner"
git add -A
git commit -m "feat(v1.2.2): 悬垂位置/桥接跨度/稳定性判断 + 接通自动支撑；清掉旧 1.2 包"
```

### 2. 推

```powershell
git push -u origin main
```

首次推会弹 GitHub 登录（浏览器点 Authorize 即可，不用输密码）。
如果远程已经有新提交被拒：

```powershell
git pull --rebase origin main
git push -u origin main
```

### 3. 发 Release（把 exe 挂上去）

网页打开 https://github.com/kcn771105/bambu-smart-tuner/releases → **Draft a new release**

- **Choose a tag** → 输入 `v1.2.2` → 点 **Create new tag on publish**
- **Release title** → `v1.2.2 — 按模型算的覆盖面加大`
- **Describe this release** → 粘下面这段：

```
修复：换喷嘴不同步机器页（v1.2.1）、打印板默认写死、控件叠字、首层温度方向、
方案关掉不还原、盒子件被重复扣分导致降速。

新增（v1.2.2）：
- 最长悬垂边 → 桥接速度 ≤30 mm/s
- 悬垂高度分布 → 上部悬垂接触面顶层 +1
- 细高 + 脚小 → 裙边加宽、首层 ≤40 mm/s
- 自动档按几何决定要不要开支撑（以前 decide() 写好但没被调用）

验证：318 passed / 2 skipped；四个不同件参数确实不同。
完整说明见包内 CHANGELOG-1.2.2.md。
```

- **Attach binaries** → 拖入
  `F:\deep seekambu_smart_tunerelease\BambuSmartTuner-v1.2.2-win64.zip`
- 点 **Publish release**

---

## 三、旧版怎么处理

- 目录里已删：`v1.2`、`v1.2.1`、`v1.2.1b` 的 zip 与解压目录；
  现在 `release/` 只剩 `v1.0`（历史存档）和 `v1.2.2`（当前版）。
- 仓库 Releases 页里旧的那几个 release，点进去 **Edit → 勾 Set as a pre-release**
  或直接 **Delete**，别留着让人下错版本。留 v1.0 当存档也行，标注 pre-release 即可。

---

## 四、以后每次改完的固定动作

```powershell
git add -A
git commit -m "fix: xxx"
git push
```

再按上面第 3 步发一个新 tag 的 Release。想一条命令搞定可以双击 `_upload_github\一键上传.bat`
（那个脚本只管 push，Release 附件仍需网页传）。

---

## 五、如果 push 报错

| 报错 | 原因 | 处理 |
|---|---|---|
| `Authentication failed` | 没登录 / token 过期 | 用 GitHub Desktop 或 `gh auth login` 重新授权 |
| `rejected — non-fast-forward` | 远程有你本地没有的提交 | `git pull --rebase origin main` 再 push |
| `remote origin already exists` | 重复添加 | `git remote set-url origin <地址>` |
| 推上去 45 MB 卡住 | 误把 `release/` 或 `dist/` 加进来 | `git reset --soft HEAD~1` 后检查 `.gitignore` |
