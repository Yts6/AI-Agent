# Git 版本控制与版本回退实战手册

> 基于 `D:\A-Code` 真实仓库的实测记录编写
> 实测环境：git version 2.56.0.windows.2 / Windows / 快照时间 2026-10-20 21:02
> 文中所有命令都在你的仓库或临时演示仓库里真跑过，输出是真实终端回显（已裁剪）

---

## 第 0 章 先看结论：你的仓库现在长什么样

在讲原理之前，先把体检结果摆出来，后面每一章都会用到这些数字。

| 项目 | 实测值 | 说明 |
|---|---|---|
| 提交数 | 35 个 | 2026-10-18 起，3 天 35 提交，节奏正常 |
| 分支 | `master` 一条 | 没有 feature 分支、没有合并记录（merge commit = 0） |
| 远程 | 空 | **没有配置任何 remote**，所有历史只在本机 |
| 标签 | 无 | 没有给任何版本起名 |
| 跟踪文件数 | 111 个 | 核心代码只占一部分 |
| 已被 .gitignore 覆盖却仍在版本库 | **67 个** | 最大的问题，见第 6 章 |
| .git 目录体积 | **320 MB** | 其中松散对象 6446 个，未打包 |
| 提交正文（body） | 0 条提交有正文 | 全部是单行标题 |

一句话总结：**提交习惯不错（清一色的 feat/fix/chore 前缀），但"只提交、不打包、不备份、不复盘"**。历史本身是健康的，脏的是内容边界和体积。

---

## 第 1 章 Git 到底是怎么存版本的

这一章回答"版本控制怎么实现的"。看懂这 7 个小节，后面所有回退命令你都能自己推出来，不用背。

### 1.1 只有三种对象：blob / tree / commit

Git 的版本库里只有三种东西：

| 对象 | 存什么 | 类比 |
|---|---|---|
| **blob** | 一个文件在某一刻的**全部内容**（不含文件名） | 一张照片 |
| **tree** | 一个目录：里面有哪些文件名，各自指向哪个 blob / 子 tree | 一份目录清单 |
| **commit** | 指向一个 tree（整棵目录树）+ 父提交 + 作者/时间 + 提交信息 | 相册里的一张时间戳 |

关键点：**Git 存的是"快照"，不是"差异"**。每次 commit，Git 把当时的整个目录树拍一张照。看着很浪费，实际上同一个文件只要内容没变，就复用同一个 blob，一个字节都不多存。

### 1.2 内容寻址：哈希是算出来的，不是随机的

blob 的 ID 就是对内容做 SHA-1，算法是：

```
sha1("blob " + 字节数 + "\0" + 文件内容)
```

在这台机器上手工验算：

```
内容 "hello\n"（6 字节）
手算   : ce013625030ba8dba906f756967f9e9ca394464a
git算  : ce013625030ba8dba906f756967f9e9ca394464a
一致   : True
```

所以：

- **同样的内容 = 同样的哈希**，这就是 Git 能自动去重的原因；
- **内容改一个字节 = 哈希全变**，这就是"改不了历史"的技术根源——你改不了过去的提交，只能新增一个指向别处的提交。

### 1.3 提交是一条链，每个提交记住它的父亲

看仓库里 HEAD 这个提交对象到底存了什么：

```
$ git cat-file -p HEAD
tree f516ee6ceb62524ab018f42967d85c3dd5058da8      <- 这一版整棵目录树的快照
parent 2808f61165d67254ffa10b5b8d684724145d1cec    <- 上一个提交
author your-name <your-email@example.com> 1792483764 +0800
committer your-name <your-email@example.com> 1792501221 +0800

feat: 思考耗时与消息时间戳、思考过程持久化、下载格式智能推荐
```

**一次提交 = 一个 tree 指针 + 一个 parent 指针 + 元信息。** 提交之间靠 parent 串成一条单向链表。`git log` 就是沿着 parent 往回走，`git reset HEAD~1` 就是"往回走一格"。

### 1.4 分支只是一个 41 字节的文本文件

```
$ cat .git/HEAD
ref: refs/heads/master
$ cat .git/refs/heads/master
10afb0618bc569da2327258ef60eebb7d45eeb66
```

就这么多。**分支不是一个文件夹、不是一份拷贝，而是"某个提交的哈希"这一个指针。**

由此可以推出三条，全都成立：

1. 建分支是**瞬间**的（写个 41 字节的文件）；
2. 切分支会把工作区文件整体换掉，所以切之前要 `git status` 干净；
3. **`git reset` 只是把这个指针挪到别处**，它不删除任何提交——这就是后面 `reflog` 能救回来的原因。

### 1.5 三个区域：工作区 / 暂存区 / 版本库

这是理解"回退"的总开关。所有回退命令的区别，本质上就是**动了这三个区域里的哪几个**。

```
   工作区                暂存区(index)              版本库(HEAD/.git)
  Working Tree    ->      Staging Area      ->       Repository
  你正在编辑的文件      下一次提交的内容清单        已经固化的历史

       |<---- git add --------|                         |
       |                      |<---- git commit --------|
       |<--------------- git diff 比较 -----------------|
       |                      |<--- git diff --staged --|
```

配套的三条查看命令，各看一段：

| 命令 | 比较的是 |
|---|---|
| `git status` | 三者总览（谁跟谁不一样） |
| `git diff` | 工作区 ↔ 暂存区（**还没 add 的改动**） |
| `git diff --staged` | 暂存区 ↔ 最新提交（**已经 add、还没提交的改动**） |

### 1.6 .git 目录里都有什么

```
.git/
├── HEAD              当前在哪个分支
├── config            本仓库配置（你的 user.name/email 就在这里）
├── index             暂存区（二进制文件，就是上图的中间层）
├── objects/          所有 blob/tree/commit 存这里（你现在是 6446 个松散文件）
│   ├── 9f/99ce0e...  松散对象：一个文件一个
│   └── pack/*.pack   打包后的对象（你还没有，见第 6 章）
├── refs/heads/       分支指针（master 就在这里）
├── refs/tags/        标签指针
└── logs/             reflog，"后悔药"存在这里
```

### 1.7 为什么 Git 快：松散对象 → 打包

你现在 `.git` 是 320 MB、6446 个松散对象。Git 平时一个一个存（松散对象），到一定数量会自动 `git gc`（garbage collect）把它们压进一个 packfile，并对相似文件做增量压缩。

第 6 章的实测：同一个仓库跑一次 `git gc`，**307.86 MiB 的松散对象变成 52.97 MiB 的 1 个 pack，15 秒，历史一条不少**。不用懂算法，记住"用完记得打包"就行。

---

## 第 2 章 日常版本控制工作流

### 2.1 一次性配置

仓库已经配好了身份（local 配置里能看到），但**全局还缺**：

```
git config --global user.name  "your-name"
git config --global user.email "your-email@example.com"
# Windows 下换行符：检出成 CRLF、提交时转 LF，避免整文件 diff
git config --global core.autocrlf true
# 中文文件名不显示成 \346\231...
git config --global core.quotepath false
# 让 git log 带颜色和图形
git config --global color.ui auto
```

### 2.2 一天的标准动作

```
git status                    # 1. 先看我在哪、改了什么
git diff                      # 2. 看看具体改了哪几行
git add AI-Agent/server.py    # 3. 挑要提交的文件（不要 git add . ）
git diff --staged             # 4. 提交前再确认一遍暂存区
git commit -m "feat: xxx"     # 5. 固化成一个版本
git log --oneline -10         # 6. 看看历史
```

**为什么不要 `git add .`**：你的仓库里躺着 `.env`、`agent.db`、`session_store/`、临时脚本。`add .` 一把梭，总有一天把密钥或 2 GB 的模型文件塞进历史——那就不是删个文件能解决的了，得改写历史。

### 2.3 提交信息规范（现在已经在用了，继续保持）

35 个提交全部是 `feat:` / `fix:` / `chore:` / `refactor:` 前缀，这是标准的 Conventional Commits，很好。补两点：

1. **超过一行要有正文**。目前 0 条提交有 body。改动大的时候，正文写"为什么改、影响什么、怎么验证"，三个月后你自己会感谢自己：

```
git commit -m "fix: 修复大文档上传失败" -m "
原因：百炼 embedding 接口限制 batch<=10，原来按 20 切分。
改动：AI-Agent/rag.py 中 BATCH_SIZE 改为 10，并加了重试。
验证：上传 3.2MB PDF 成功，切分成 412 个片段全部入库。
"
```

2. **一个提交只做一件事**。`feat:` 里混进 `chore:` 会让回退时无法只退一半。

### 2.4 .gitignore：规则、优先级和你踩的坑

基本规则：

| 写法 | 含义 |
|---|---|
| `data/` | 忽略任意层级下叫 data 的目录 |
| `/data/` | 只忽略**根目录**的 data |
| `*.log` | 忽略所有 .log 文件 |
| `!keep.log` | 例外：不忽略 keep.log |
| `**/node_modules/` | 递归任意深度 |

**两个必须知道的坑**（你都踩了）：

**坑一：.gitignore 只对"未跟踪"的文件生效。** 已经被 commit 过的文件，即使后来写进 .gitignore，Git 照样继续跟踪它。用这条命令查出来：

```
$ git ls-files -i -c --exclude-standard | wc -l
67
```

**67 个文件已经在忽略名单里，却还在版本库里。** 详见第 6 章。

**坑二：忽略规则写太宽会误伤。** 你的 `.gitignore` 里有 `_*.py`、`*.bat`、`test/`、`Hbuilder/`、`rainy-street/`，这些把**整个目录**从版本控制里排除了。如果里面以后有值得留的代码（比如 `test/` 里是正经单元测试），你会发现它死活 add 不进去。

### 2.5 分支：现在只有一条 master，这是最大的流程短板

35 个提交全在 master 上直推，没有一次 merge。这意味着：

- 任何一次提交出问题，影响的都是主线；
- 没法"边开发边保留可用版本"；
- 没法做 code review / PR。

改成这样（feature branch 工作流）：

```
# 1. 开一个新分支做新功能（瞬间完成）
git switch -c feat/export-word

# 2. 在新分支上随便提交，坏了也不影响 master
git add AI-Agent/docgen.py
git commit -m "feat: 支持导出 Word"

# 3. 做完了，切回 master 合进来
git switch master
git merge --no-ff feat/export-word     # --no-ff 保留"这里合并过"的痕迹

# 4. 删掉分支（只是删指针，提交不会丢，还在 master 上）
git branch -d feat/export-word

# 5. 做废了？直接扔掉
git switch master
git branch -D feat/export-word
```

`git switch` 和 `git checkout` 是一回事，新命令语义更清楚（switch 切分支，restore 还原文件）。你用的是 2.56，放心用新命令。

### 2.6 标签：给"能用的版本"起个名字

提交哈希 `10afb06` 没人记得住，`v1.0` 记得住。发版、交作业、答辩前，打一个：

```
git tag -a v1.0 -m "第一版可演示：RAG + 导出 + 历史搜索"
git tag -l                    # 看所有标签
git show v1.0                 # 看这个版本改了什么
git describe --tags           # 当前 HEAD 距离最近标签多远
```

目前 0 个标签。建议现在就把当前这条能跑的版本打成 `v0.1`，以后回退时"退回 v0.1"比"退回第 23 个提交"靠谱得多。

### 2.7 远程：现在所有代码只有一份

`git remote -v` 输出为空——**35 个提交、3 天心血，只存在于 `D:\A-Code\.git` 这一块硬盘上**。硬盘挂了、误删了，就全没了。

最小成本补救（GitHub / Gitee 私有库都行）：

```
git remote add origin git@github.com:你的账号/A-Code.git
git push -u origin master
```

**注意：先做完第 6 章的清理再推。** 一旦含大文件的历史推上去，再想删就得 force push 改写历史，很麻烦。

---

## 第 3 章 版本回退：九种场景对照表

这一章是核心。**先看这张表定位你的场景，再跳到对应小节。**

| # | 你的处境 | 命令 | 改历史？ | 危险度 |
|---|---|---|---|---|
| A | 文件改坏了，还没 commit | `git restore <文件>` | 否 | 高（改动丢失） |
| B | add 错了文件 | `git restore --staged <文件>` | 否 | 安全 |
| C | 提交信息写错了，还没 push | `git commit --amend` | 是 | 安全（仅本地） |
| D | 想退回上一个版本，还没 push | `git reset --hard HEAD~1` | 是 | 高（需 reflog 兜底） |
| E | 刚 reset 完就后悔了 | `git reflog` + `git reset --hard <哈希>` | 是 | 安全 |
| F | 已 push 的提交要撤销 | `git revert <哈希>` | **否**（新增提交） | 安全 |
| G | 只想撤销历史中间某一个提交 | `git revert <那个哈希>` | 否 | 安全 |
| H | 只想看/取回旧版本里的一个文件 | `git show <哈希>:<路径>` | 否 | 安全 |
| I | 改到一半要切分支 | `git stash` | 否 | 安全 |

下面每一条都有实测输出。

### 场景 A：文件改坏了，还没 commit

**最常用、最安全的一条。**

```
$ git status --short
 M app.py

$ git restore app.py            # 丢弃工作区改动，回到上次 commit 的样子

$ cat app.py
print("v1")
print("v2")
```

- 老写法（等价）：`git checkout -- app.py`
- **只想丢一个文件**：把文件名换成那个文件
- **全丢**：`git restore .`（危险，先 `git status` 看清楚）

> 注意：这条命令丢掉的改动**没有 commit 过，reflog 救不回来**。它直接覆盖工作区，没有后悔药。

### 场景 B：add 错了 / 想撤销暂存

```
$ git status --short
 M app.py
A  tmp.py           <- 已经 add 进暂存区（左边那一列的 A）

$ git restore --staged tmp.py

$ git status --short
 M app.py
?? tmp.py           <- 回到未跟踪状态，文件本身没动
```

- 老写法：`git reset HEAD tmp.py`
- 关键：`--staged` 只动暂存区，**工作区文件原样保留**

### 场景 C：提交信息写错了，或漏了一个文件

**还没 push 的时候用，会改写最后一次提交。**

```
# 只改信息
git commit --amend -m "fix: 改成正确的描述"

# 漏了文件：先 add 再 amend，会合并进上一个提交
git add 忘了的文件.py
git commit --amend --no-edit      # --no-edit 表示沿用原来的提交信息
```

> 已经 push 过的提交不要 amend。它会生成一个新的提交对象，和远程历史分叉，下次 push 会被拒。

### 场景 D：退回上一个版本（本地未 push）

这是"版本回退"最常问的一条。实测：

```
$ git log --oneline --decorate
a597581 (HEAD -> main) fix: 第三版（其实是 bug）
a055de5 feat: 第二版
158f234 feat: 第一版

$ git reset --hard HEAD~1
HEAD is now at a055de5 feat: 第二版

$ git log --oneline --decorate
a055de5 (HEAD -> main) feat: 第二版
158f234 feat: 第一版

$ cat app.py
print("v1")
print("v2")                     <- 第三版的内容已经从工作区消失
```

`HEAD~1` 的几种写法：

| 写法 | 含义 |
|---|---|
| `HEAD~1` | 上一个提交（往回 1 格） |
| `HEAD~3` | 往回 3 格 |
| `HEAD^` | 同 `HEAD~1` |
| `a055de5` | 直接指定某个提交的哈希 |
| `v1.0` | 直接指定某个标签 |

**`--hard` / `--soft` / `--mixed` 到底差在哪**——看第 4 章，这是最容易搞混的地方。

### 场景 E：刚 reset 完就后悔了（reflog 救场）

**这是 Git 最像"后悔药"的功能，务必记住。**

```
$ git reflog
a055de5 HEAD@{0}: reset: moving to HEAD~1           <- 刚才那步
a597581 HEAD@{1}: commit: fix: 第三版（其实是 bug）  <- 被"丢掉"的提交还在！
a055de5 HEAD@{2}: commit: feat: 第二版
158f234 HEAD@{3}: commit (initial): feat: 第一版

$ git reset --hard a597581
HEAD is now at a597581 fix: 第三版（其实是 bug）

$ cat app.py
print("v1")
print("v2")
print("v3-有bug")               <- 完整找回来了
```

原理回到 1.4：`reset` 只是把分支指针挪走，**提交对象还躺在 `.git` 里**，reflog 记着它曾经被谁指向过。

三条实用变体：

```
git reflog                      # 看最近 90 天的 HEAD 移动记录
git reset --hard HEAD@{2}       # 直接按 reflog 编号回退
git reset --hard abc1234        # 按哈希回退
```

> 边界：reflog 默认只保留 90 天，且 `git gc --prune=now` 会把没有被任何分支/标签指向的对象物理删除。**过了这个窗口，才是真的没了。**

### 场景 F：已经 push 出去的提交要撤销（revert）

**改历史是禁忌，revert 是正解。它不删除任何东西，只是"再加一个把改动反过来的新提交"。**

```
$ git revert --no-edit HEAD
[main 22718ff] Revert "fix: 第三版（其实是 bug）"
 1 file changed, 1 deletion(-)

$ git log --oneline --decorate
22718ff (HEAD -> main) Revert "fix: 第三版（其实是 bug）"   <- 新提交
a597581 fix: 第三版（其实是 bug）
a055de5 feat: 第二版
158f234 feat: 第一版

$ cat app.py
print("v1")
print("v2")                     <- 内容回去了，历史一条没少
```

**reset 和 revert 的根本区别：**

| | `git reset` | `git revert` |
|---|---|---|
| 历史 | 往后挪指针，**看起来像没发生过** | 新增一个反向提交，**历史完整保留** |
| 冲突 | 可能大量冲突 | 可能冲突（逐个解决即可） |
| 已推送的仓库 | 必须 force push，会打断别人 | 普通 push 即可 |
| 适用 | 本地、个人分支 | **共享分支、已推送** |

口诀：**没推过用 reset，推过了用 revert。**

### 场景 G：只想撤销历史中间的某一个提交

```
git revert a597581                 # 只把这一次的改动反向应用
git revert --no-commit a1 b2 c3    # 连续撤多个，先不提交，方便一起改
```

### 场景 H：只看 / 只取回旧版本里的一个文件

**不想动整个仓库，只想看看三天前那个文件长什么样。**

```
# 只看内容，不落盘
git show a055de5:app.py
git show HEAD~5:AI-Agent/server.py | head -50

# 把旧版本的这个文件取回工作区（会覆盖当前文件！先备份）
git restore --source=a055de5 app.py

# 老写法
git checkout a055de5 -- app.py
```

**这个技巧非常实用**：某个文件被改崩了，但不想整体回退，就单独把那个文件从旧提交里捞出来。

### 场景 I：改到一半要切分支，先 stash

```
$ git stash push -m "半成品"
Saved working directory and index state On main: 半成品

$ git status --short
                                <- 工作区干净了，可以切分支

$ git stash list
stash@{0}: On main: 半成品

$ git stash pop                 <- 回到这个分支后，把改动拿回来
Dropped refs/stash@{0}
```

- `git stash pop` = 应用 + 删除；`git stash apply` = 只应用，保留备份
- `git stash drop` = 丢弃；`git stash clear` = 全清（危险）
- 忘了 `git commit` 就切分支报错时，90% 是因为这个

### 场景 J：整个分支搞砸了，回到远程最新

```
git fetch origin
git reset --hard origin/master     # 本地 master 强制定位到远程最新
```

（现在没有 remote，这条暂时用不上，等 2.7 配好了就常用。）

---

## 第 4 章 reset 的三种模式：一张图讲透

这是**最容易混、也最容易出事**的知识点。

```
                提交历史(HEAD)      暂存区(index)      工作区(文件)
--soft              挪回             不变             不变       -> 改动全在"待提交"
--mixed (默认)      挪回             重置             不变       -> 改动全在"未暂存"
--hard              挪回             重置             重置       -> 改动彻底消失
```

具体用法：

| 场景 | 用哪个 | 结果 |
|---|---|---|
| 提交早了，想撤回来重新整理再提交一次 | `--soft` | 文件都在，改动都在暂存区，`git status` 显示 `M ` |
| 提交早了，想撤回来重新挑选哪些文件提交 | `--mixed`（默认） | 文件都在，改动变"未暂存"，需要重新 add |
| 彻底不要了，代码也不要了 | `--hard` | 文件被覆盖，**没有 commit 的改动永久丢失** |

实测对照：

```
$ git reset --soft HEAD~1      # 提交没了，但改动还在暂存区
$ git status --short
M  app.py                     # 左列 M = 已暂存

$ git reset --mixed HEAD~1     # 改动还在，但退出了暂存区
$ git status --short
 M app.py                     # 右列 M = 未暂存

$ git reset --hard HEAD~1      # 改动和文件一起没了
$ git status --short
                              # 干净
```

> 记住一句话：**`--hard` 是唯一会真正删掉你代码的那个。**

---

## 第 5 章 回退的安全底线

### 5.1 真正不可逆的只有三个操作

| 操作 | 为什么不可逆 |
|---|---|
| `git reset --hard` 丢掉**未提交**的改动 | 从来没进过对象库，reflog 里也没有 |
| `git clean -fdx` | 直接删未跟踪文件，包括 .env、数据、模型 |
| `git push --force` 覆盖远程 | 别人拉过旧历史会被打乱，旧提交成为孤儿 |

其他操作（reset 已提交的内容、revert、amend、rebase）**都有 reflog 兜底**，理论上都能找回来。

### 5.2 回退前先做这三件事

```
git status                    # 1. 工作区干净吗？
git log --oneline -5          # 2. 记下现在在哪（截图/复制哈希）
git branch backup-20261020    # 3. 建个备份分支再动手，出事直接切回去
```

第 3 条是**最省事的保险**：一个分支指针而已，零成本。

### 5.3 已经推送的历史，永远不要改写

你仓库的 reflog 里有一条 `filter-branch: rewrite` 记录——说明之前用 filter-branch 改写/清理过历史。这种操作：

- 会为每个提交生成**全新的哈希**；
- 已 push 的远程库会分叉，必须 `--force` 覆盖；
- 协作者必须重新 clone。

本地个人仓库随便玩（有 reflog 兜底）；一旦有别人在用，改用 revert。

---

## 第 6 章 体检结论：现在这套流程的 8 个问题

按严重程度排序，每条都给了可以直接复制的修复命令。**放在最后讲，是因为你要先看懂前面 5 章，才知道为什么要这么改。**

### 问题 1 ★★★★★ 67 个已被忽略的文件还在版本库里

```
$ git ls-files -i -c --exclude-standard | wc -l
67
```

分布：

| 目录 | 数量 | 是什么 | 该不该在库里 |
|---|---|---|---|
| `_backup_agent_git/` | 约 30 | **一整份 .git 目录的拷贝**（含 objects/refs/hooks） | 绝对不该 |
| `_backup_old_python/` | 7 | pip freeze / 版本快照 | 不该 |
| 根目录 `_*.py` / `_*.json` | 9 | 临时调试脚本 | 不该 |
| `_research/` | 5 | 爬取的数据 JSON | 不该 |
| `AI-Agent/session_store/` | 3 | 运行时会话 JSON | 不该 |
| `test/` | 2 | 临时测试 | 不该（或改成正经测试再留下） |
| `_backup_remote_readme/` | 1 | 远端 README 备份 | 不该 |

**注意：规则已经写好了，只是"已经跟踪"的文件不受规则约束。** 修复（只从索引移除，**不删本地文件**）：

```
git rm -r --cached _backup_agent_git _backup_old_python _backup_remote_readme _research test AI-Agent/session_store
git rm --cached _elapsed.py _histtime.py _histtime2.py _restreason.py _savereason.py _timeblk.json _timescss.py _wtime.py _dbcreated.py
git status --short
git commit -m "chore: 从版本库移除已被 .gitignore 覆盖的 67 个文件"
```

验证：再跑一次 `git ls-files -i -c --exclude-standard | wc -l`，应该输出 0。

> 这一步只是让**未来**不再跟踪。历史里那些提交仍然存在（见问题 2 和问题 4）。

### 问题 2 ★★★★☆ .git 有 320 MB，6446 个松散对象没打包

```
$ du -sh .git
320M
$ git count-objects -vH
count: 6444
size: 307.86 MiB
in-pack: 0
packs: 0
```

在副本上实测 `git gc` 的效果（**原仓库没动**）：

```
--- gc 前 ---
count: 6444 / size: 307.86 MiB / packs: 0
--- git gc --prune=now ---
real  0m15.279s
--- gc 后 ---
count: 0 / size: 0 / in-pack: 4547 / packs: 1 / size-pack: 52.97 MiB
--- 历史完整性 ---
34 个提交、4513 个对象，一条不少
```

**320 MB → 53 MB，15 秒，历史无损。** 这属于纯收益，立刻可做：

```
git gc --prune=now
```

以后想让它自动：`git config --global gc.auto 6700`（默认就是 6700，你只是还没触发过）。

> `--prune=now` 会顺手清掉不可达对象（reflog 里没有的）。想更保守就用 `git gc`（保留 2 周）。

### 问题 3 ★★★★☆ 2 GB 的 _research/ 和一堆备份目录躺在仓库根目录

`_research` 实测 2.3 GB。虽然已被 .gitignore 挡住（除了那 5 个已跟踪的），但它就在 `D:\A-Code` 里，任何一次 `git status --ignored`、任何一次 IDE 索引都会被它拖慢。

建议搬到仓库外，例如 `D:\A-Archive\`。

### 问题 4 ★★★☆☆ 历史里有 112 MB 的大文件

```
$ git log --oneline --all -- tools/cpolar/cpolar.exe
4391de8 chore: 忽略运行时数据与工具目录
f268982 feat: 查询改写、重排、RAG 评估（Recall 96%→100%, MRR 0.96→1.0）
```

| 文件 | 大小 | 现状 |
|---|---|---|
| `tools/cpolar/cpolar.exe` | 19.6 MB | 已从 HEAD 删除，但历史里还在 |
| `rainy-street/node_modules/` 若干 exe/wasm | 10.4 MB + 4.1 MB + … | 同上 |
| `rainy-street/shots/*.png` | 约 1.9 MB × 2 | 同上 |

可达对象合计 112 MB（打包后 53 MB 就是这么来的）。**这些不影响日常使用，只影响 clone 速度**。如果将来要推到远程、或者想彻底瘦身，再用 `git filter-repo` 清理（注意：会改写所有历史哈希，必须在推送前做）。

现在**不建议动**——收益（clone 快一点）远小于风险（重写 35 条历史）。

### 问题 5 ★★★☆☆ 没有远程仓库

见 2.7。3 天 35 次提交只存在于一块硬盘上，这是**唯一可能让你"全部白干"的问题**。优先级应该在技术问题之上。

### 问题 6 ★★★☆☆ 没有分支、没有合并

35 个提交全在 master，0 次 merge。见 2.5。

### 问题 7 ★★☆☆☆ 0 个标签

见 2.6。当前能跑的版本建议马上打 `v0.1`。

### 问题 8 ★★☆☆☆ 小瑕疵三连

| 现象 | 影响 | 修复 |
|---|---|---|
| `agent-learning/` 是 gitlink（mode 160000）但没有 `.gitmodules` | 别人 clone 下来是**空目录** | 要么补 `git submodule add`，要么去掉 gitlink 改为普通跟踪或彻底忽略 |
| `core.autocrlf=true` 但没有 `.gitattributes` | Windows/Linux 混合开发时换行符混乱 | 加一个 `.gitattributes` 显式声明 |
| 提交正文 100% 为空 | 半年后看不懂当时为什么改 | 见 2.3 |

`.gitattributes` 建议内容：

```
* text=auto
*.py   text eol=lf
*.sh   text eol=lf
*.ps1  text eol=crlf
*.bat  text eol=crlf
*.png  binary
*.db   binary
```

---

## 第 7 章 建议的执行顺序

按"收益 / 风险"排，从今天到一个月：

| 顺序 | 做什么 | 耗时 | 风险 |
|---|---|---|---|
| **今天** | 问题 1：`git rm -r --cached` 清 67 个文件 | 2 分钟 | 无 |
| **今天** | 问题 2：`git gc --prune=now` 320MB→53MB | 1 分钟 | 无 |
| **今天** | 打标签 `git tag -a v0.1` | 10 秒 | 无 |
| **本周** | 问题 5：建远程私有库并 push | 10 分钟 | 无 |
| **本周** | 问题 8：补 `.gitattributes` 和 `.gitmodules` | 10 分钟 | 无 |
| **下周** | 问题 6：下一次改动开始用 feature branch | 习惯问题 | 无 |
| **以后** | 每次大改动 `git commit` 都写正文 | 习惯问题 | 无 |
| **暂缓** | 问题 4：filter-repo 清大文件 | — | 高 |

---

## 附录 A 命令速查表

### 看

```
git status                        当前状态
git diff                          未暂存的改动
git diff --staged                 已暂存的改动
git log --oneline --graph --all   历史全景图
git log -p 文件                   某个文件的修改历史
git show <哈希>                   某次提交改了什么
git blame 文件                    每一行是谁改的
git reflog                        我最近都干了什么（后悔药）
```

### 提交

```
git add <文件>                    加入暂存区
git add -p                        逐个片段挑选（强烈推荐）
git commit -m "说明"              提交
git commit --amend                改最后一次提交
git reset HEAD~1                  撤销最后一次提交（保留改动）
```

### 回退

```
git restore <文件>                      丢弃工作区改动
git restore --staged <文件>             取消暂存
git restore --source=<哈希> <文件>      从旧版本取回单个文件
git reset --soft  <哈希>                回退提交，改动留在暂存区
git reset --mixed <哈希>                回退提交，改动留在工作区（默认）
git reset --hard  <哈希>                回退提交，改动丢弃（危险）
git revert <哈希>                       新增反向提交（已推送时用）
git branch 备份-日期                    动手前先建备份分支
```

### 分支 / 标签 / 远程

```
git switch -c feat/xxx            新建并切换分支
git switch master                 切回主分支
git merge --no-ff feat/xxx        合并并保留合并记录
git branch -d feat/xxx            删除已合并分支
git tag -a v1.0 -m "说明"         打标签
git tag -l                        列出标签
git remote add origin <url>       配置远程
git push -u origin master         首次推送并建立跟踪
git fetch && git status           看远程有没有新东西
```

---

## 附录 B 常见报错怎么办

| 报错 | 原因 | 解决 |
|---|---|---|
| `fatal: not a git repository` | 不在仓库里 | 切到有 `.git` 的目录 |
| `error: Your local changes would be overwritten` | 有未提交改动，切分支/拉取会冲突 | 先 `git stash` 或 `git commit` |
| `fatal: refusing to merge unrelated histories` | 两个不相干的历史合并 | `git pull --allow-unrelated-histories` |
| `! [rejected] ... non-fast-forward` | 远程有新提交 | `git pull --rebase` 后再 push |
| `error: failed to push some refs`（reset 之后） | 本地历史和远程分叉 | 要么 `--force-with-lease`，要么 revert 重来 |
| `fatal: pathspec did not match` | 文件不在跟踪列表里 | 检查路径；被 ignore 的文件要先 `git add -f` |
| `warning: LF will be replaced by CRLF` | 换行符转换提示 | 无害；想彻底解决用 `.gitattributes` |
| 中文显示成 `\346\231\272` | 路径转义 | `git config --global core.quotepath false` |

---

## 附录 C 本次实测环境

| 项目 | 值 |
|---|---|
| 仓库 | `D:\A-Code` |
| git | 2.56.0.windows.2 |
| 快照时间 | 2026-10-20 21:02 |
| 提交数 | 35（HEAD = 10afb06） |
| 分支 | master |
| 远程 | 无 |
| .git 体积 | 320 MB / 6446 松散对象 |
| 已跟踪文件 | 111 |
| 忽略但已跟踪 | 67 |

文中所有"实测"输出，来自三处：

1. 在 `D:\A-Code` 仓库上执行的只读命令（`git log` / `cat-file` / `ls-files` / `count-objects` 等）；
2. 在临时目录下新建的演示仓库（跑完即删）里执行的读写命令；
3. 对 `.git` 的**副本**执行的 `git gc` 实验（原仓库未受影响，副本已删除）。

除了读取，本手册没有对你的仓库做任何修改。
