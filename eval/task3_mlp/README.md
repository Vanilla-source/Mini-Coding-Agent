# 任务三模拟题｜简单神经网络实现

对应真实考核：**任务三（25 分 · 综合）**
范围：Python + PyTorch 完成小规模分类任务——读数据、搭简单前馈网络（MLP）、训练、输出预测。
教师现场给带标签训练集 + 预测用测试特征，真实标签保留用于评分。

## 待补内容

| 文件 | 内容 | 状态 |
|---|---|---|
| `task.md` | 任务描述：数据格式、输出格式、运行命令 | 待写 |
| `data/train.csv` | 带标签训练集 | 待造 |
| `data/test_features.csv` | 只含特征，无标签 | 待造 |
| `data/test_labels.csv` | 真实标签，**不进工作目录**，只给判分用 | 待造 |
| `grade.py` | 算 accuracy 并与阈值比较，`grade(workspace) -> (score, detail)` | 待写 |

## 数据

自己造即可，重点在流程跑通而不是刷精度：
- 三类分类，每类 150~200 条
- 4~6 个数值特征，类别间留出可分的间隔
- `train.csv` 列名：`f1,f2,f3,f4,label`
- `test_features.csv` 列名：`f1,f2,f3,f4`

## 题面必须写死的约束

```
运行命令：python predict.py
输入：train.csv、test_features.csv（同在项目根目录）
输出：predictions.csv，两列：id,label（id 为测试行序号，从 0 开始）
```

## 判分

- 读 `predictions.csv`，与 `test_labels.csv` 对行算 accuracy
- 按"格式正确"（文件存在、列名对、行数对）+ "accuracy 超过阈值" 两段给分
- 同时记录训练耗时，确认普通 CPU 能在时限内跑完

## 注意事项

真实考核写的是"正式成绩不单凭训练过程中的准确率判定"——所以判分只看**最终预测文件**，
对应 `grade.py` 里必须读 `predictions.csv` 而不是看 Agent 自己打印的 accuracy。
