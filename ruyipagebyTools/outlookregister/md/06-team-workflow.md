# 06 - 团队协作流程

## 团队阵容

| 成员 | slot_id | 角色 | 职责 |
|---|---|---|---|
| Claude Code | 019fb6c5-3e46-7e10-b3f1-b3f38d2ba2ae | lead | 拆任务、派发、复核审核结论、commit、维护文档 |
| 代码执行和审核(写码 Codex) | 019fb6c5-6802-7ce0-a0f4-337c1e564c30 | teammate | 实现 + 论证(不审自己的码) |
| 代码审核员 | 019fb708-9f58-7bc2-a5b9-1bde6ffab56f | teammate | 独立复审 diff,给"通过/打回+理由" |

## 标准流程

复杂决策(如异常分类标准、intercept API 可行性、方案甲/乙):
1. 派 Codex **论证**(只论证不改码)→ 我复核
2. 派 Codex **实现** → 贴 diff + py_compile
3. 派审核员 **复审** → 给通过/打回
4. 我 **复核** 审核结论(查日志/源码)
5. 通过 → **commit**

简单修改:直接派实现 → 复审 → 复核 → commit。

## idle 处理

- teammate idle 是正常收尾,**不是错误**。
- 审核员有时 idle 但没返回结论(疑似 runtime_starting 延迟):催 1-2 次,仍无果则 **lead 自行复核推进**,不卡在审核环节。

## 已用过的模式

- **方案甲/乙选择**:用户拍板行为决策(PX 失败代理是否保留、timeout 是否重试)。
- **查证前置**:改前先查证事实(如 NS_ERROR_* 是否进 run_batch except),避免白改。
- **日志实证**:扫 `_logs/batch_*.log` 的异常分布,用真实证据校准判断。
- **库源码核对**:读 ruyipage 库(interceptor.py/firefox_base.py)确认 API 行为,不猜。
