# 任务一模拟题｜Python 基础数据结构

对应真实考核：**任务一（15 分 · 基础）**
范围：栈、队列、链表、树等常见数据结构及基本操作，按接口说明实现，正确处理空结构与重复数据。

## 待补内容

| 文件 | 内容 | 状态 |
|---|---|---|
| `task.md` | 给 Agent 的任务描述（含函数签名、输入输出格式） | 待写 |
| `data/` | 该题不需要数据文件 | — |
| `grade.py` | 隐藏用例判分，`grade(workspace) -> (score, detail)` | 待写 |

## 设计建议

题面建议用 **LRU Cache**，因为它能同时覆盖三件事：
- 基本接口：`get(key)`、`put(key, value)`、容量上限
- 边界条件：空容器、容量为 1、重复 put 同一 key（应更新值并刷新位置）
- 复杂度暗示：要求 `O(1)`，逼出"哈希表 + 双向链表"的正确实现，而不是 list 暴力扫描

题面里必须写死：
```
文件：solutions/lru_cache.py
类名：LRUCache
方法：__init__(capacity) / get(key) -> value 或 -1 / put(key, value) -> None
```

## 判分

`grade.py` 用隐藏 pytest 用例（10~15 条）跑 `solutions/lru_cache.py`，按通过比例给分。
参考真实考核的评分依据："基本功能、接口符合程度及边界输入测试"。
