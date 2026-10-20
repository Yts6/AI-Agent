# Git 回退速查卡（一页版）

> 贴墙用。完整版见《Git 版本控制与版本回退实战手册》。

## 一、先判断：你的改动到哪一步了？

| 改动状态 | 想撤销 | 命令 |
|---|---|---|
| 只改了文件，没 add | 丢弃改动 | `git restore <文件>` |
| 已经 add | 退回未暂存 | `git restore --staged <文件>` |
| 已经 commit，没 push | 整个提交撤掉 | `git reset --hard HEAD~1` |
| 已经 commit，没 push（只要改信息） | 改最后一次提交 | `git commit --amend` |
| 已经 push | **不能 reset** | `git revert <哈希>` |
| 刚 reset 完后悔 | 找回 | `git reflog` 然后 `git reset --hard <哈希>` |

## 二、reset 三种模式

| 模式 | 提交历史 | 暂存区 | 工作区文件 | 什么时候用 |
|---|---|---|---|---|
| `--soft` | 后退 | 保留 | 保留 | 想重新组织这次提交 |
| `--mixed`（默认） | 后退 | 清空 | 保留 | 想重新挑文件提交 |
| `--hard` | 后退 | 清空 | **覆盖** | 真的不要了（唯一会删代码的） |

## 三、九条高频命令

```
git status                       现在什么状态
git log --oneline --graph --all  历史全景
git diff                         还没 add 的改动
git diff --staged                已经 add 的改动
git restore <文件>               丢弃工作区改动
git restore --staged <文件>      取消暂存
git reset --soft  HEAD~1         撤销提交，改动留着
git reset --hard  <哈希>         回到某个版本
git revert <哈希>                反向提交（已 push 用这个）
```

## 四、revert vs reset

| | reset | revert |
|---|---|---|
| 历史 | 指针后退，像没发生过 | 新增一个反向提交 |
| 已推送 | 必须 force push | 普通 push |
| 适合 | 本地、个人分支 | **共享分支** |

**口诀：没推过用 reset，推过了用 revert。**

## 五、找回丢失的提交（reflog）

```
git reflog                       # 看 HEAD 最近 90 天怎么移动的
git reset --hard HEAD@{2}        # 按编号回去
git reset --hard a597581         # 按哈希回去
```

原理：reset 只挪指针，提交对象还在 .git 里。

## 六、回退前的三件保险

```
git status                    # 工作区干净吗
git log --oneline -5          # 记下现在在哪
git branch backup-$(date +%Y%m%d)   # 先建备份分支再动手
```

## 七、三条铁律

1. **没提交的改动，reflog 救不了**——`--hard` 和 `git clean` 是唯一真删代码的。
2. **推过的历史不要改写**——`amend` / `rebase` / `filter-branch` 只用在本地。
3. **提交前看清楚**——`git add .` 之前先 `git status`，别把密钥和大文件带进去。

## 八、Windows 下三条环境配置

```
git config --global core.autocrlf true      # 换行符自动转换
git config --global core.quotepath false    # 中文路径不乱码
git config --global color.ui auto           # 彩色输出
```

## 九、日常节奏

```
# 开分支
git switch -c feat/xxx
# 改代码 → 挑文件 → 提交
git add <具体文件>
git commit -m "feat: 做了什么"
# 合并回主线
git switch master
git merge --no-ff feat/xxx
# 打版本
git tag -a v1.0 -m "第一版可演示"
```

---

**记住三个词就够了：**

- **restore** = 还原本地文件
- **reset** = 历史指针后移（本地）
- **revert** = 新增反向提交（远程）
