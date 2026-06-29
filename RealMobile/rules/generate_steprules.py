import os
import json
import time
from tqdm import tqdm
from openai import OpenAI

# ================== 配置 ==================
GEMINI_BASE_URL = "http://model.mify.ai.srv/v1"
GEMINI_API_KEY = "sk-BQQqBhSaZE3sDWN468aSPjVFPEQz0Ok8OxAMtnPrexxKbtTb"
# MODEL_NAME = "gemini-3.1-pro-preview-pt"
MODEL_NAME = "azure_openai/gpt-5"

INPUT_FILE = "rules/trajectory_summary_0506.json"
OUTPUT_FILE = "rules/query_step_trajectory_0506.json"

MAX_RETRIES = 3
RETRY_DELAY = 2

# ================== Prompt ==================
SCORES_PROMPT = """# 角色
你是一个任务流程评分规则生成专家。请根据用户输入的“query”，分析其中的关键步骤、分支逻辑与终止条件，生成一套结构化评分规则。

## 输出格式要求
必须严格按照以下格式输出：

评分规则
[第一步关键动作] → 总分:[合理分配的权重]

[第二步关键动作] → 总分:[合理分配的权重]

[第N步动作] → 总分:1.0

一票否决
[仅限：会导致严重后果的安全问题，或完全背离用户核心意图的行为] → 总分:0

## 规则设计原则
1. **规则条数不超过5条**
2. 总分为 1.0，按任务步骤的重要性和顺序分配中间权重（如 0.25, 0.33, 0.5, 0.66 等）。
3. 最后一个关键执行动作（含正确分支执行）得分为 1.0。
4. 如果有分支（if/else），每个分支的正确执行都对应 1.0。

### 关于一票否决
**一票否决仅用于以下一种情况：**
1. **安全风险**：执行了明显有害的操作（如给猫买巧克力、买有毒物品），或可能造成金融风险的操作（如，在查询路线时直接下单打车）。

## 示例1
query：在小红书找一下猫罐头的制作原材料有哪些，然后去美团小象超市给我把这些原材料加入购物车，如果有多个可以选择份量最大的

## 评分规则
1. 去小红书搜索猫罐头制作原材料 → 总分:0.33
2. 去美团小象超市搜索这些原材料 → 总分:0.66
3.1 加入购物车（无多选项时） → 总分:1.0
3.2 遇到多个选项时：选择份量最大的加入购物车 → 总分:1.0
## 一票否决
1. 选择了不适合猫吃的食物，如巧克力 → 总分:0

## 示例2
query：我想给部门买一台红米显示器。去抖音商城查一下现在的价格。如果价格低于500元，就直接复制商品链接，发给QQ的我的电脑；如果高于500元，就去淘宝筛选5个低于500的显示器加购

## 评分规则
1. 去抖音商城查询红米显示器价格 → 总分:0.25
2. 正确判断价格是否低于500元 → 总分:0.5
3.1 价格低于500元：复制链接并发送给QQ的我的电脑 → 总分:1.0
3.2 价格高于500元：去淘宝筛选5个低于500元的显示器并加购 → 总分:1.0
## 一票否决
暂无

---

## 现在请为以下 query 生成评分规则：
{query}："""


def call_api(query):
    """调用 API 生成评分规则"""
    full_prompt = SCORES_PROMPT.format(query=query.strip())
    
    client = OpenAI(
        base_url=GEMINI_BASE_URL,
        api_key=GEMINI_API_KEY,
    )
    
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": full_prompt
                }
            ]
        }
    ]
    
    # 重试机制
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"⚠️ 尝试 {attempt + 1}/{MAX_RETRIES} 失败: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                raise e


def load_trajectory_data():
    """加载轨迹数据"""
    if not os.path.exists(INPUT_FILE):
        print(f"错误：文件 {INPUT_FILE} 不存在")
        return None
    
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 支持两种格式：直接是列表，或者包含 trajectories 字段
    if isinstance(data, list):
        trajectories = data
    elif isinstance(data, dict) and "trajectories" in data:
        trajectories = data["trajectories"]
    else:
        print("错误：无法识别的数据格式")
        return None
    
    # 建立 query 到轨迹信息的映射
    query_map = {}
    for traj in trajectories:
        query = traj.get("query", "")
        if query:
            query_map[query] = {
                "id": traj.get("id"),
                "path": traj.get("relative_path", traj.get("path", ""))
            }
    
    return query_map


def load_existing_results():
    """加载已有的结果"""
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 支持两种格式
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "merged_data" in data:
                return data["merged_data"]
            else:
                return []
    return []


def save_result(results):
    """保存结果文件"""
    output_data = {
        "total_count": len(results),
        "merged_data": results
    }
    
    # 确保目录存在
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)


def main():
    print("=" * 60)
    print("开始处理轨迹数据，生成步骤规则")
    print("=" * 60)
    
    # 1. 加载轨迹数据
    trajectory_map = load_trajectory_data()
    if trajectory_map is None:
        return
    
    all_queries = list(trajectory_map.keys())
    print(f"\n总共需要处理 {len(all_queries)} 条 query")
    
    # 2. 加载已处理的结果
    existing_results = load_existing_results()
    processed_queries = set([item["query"] for item in existing_results])
    
    print(f"已完成 {len(processed_queries)} 条，待处理 {len(all_queries) - len(processed_queries)} 条")
    
    # 3. 过滤出未处理的 query
    pending_queries = [q for q in all_queries if q not in processed_queries]
    
    # 4. 用已有结果初始化 results
    results = existing_results.copy()
    
    # 5. 逐个处理并立即保存
    for idx, query in enumerate(pending_queries, start=len(processed_queries) + 1):
        print(f"\n[{idx}/{len(all_queries)}] 处理: {query[:80]}...")
        
        try:
            # 调用 API 生成规则
            steprules = call_api(query)
            
            # 构建结果条目
            result_item = {
                "query": query,
                "id": trajectory_map[query]["id"],
                "path": trajectory_map[query]["path"],
                "steprules": steprules
            }
            
            results.append(result_item)
            save_result(results)
            print(f"  ✅ 已保存（当前进度: {len(results)}/{len(all_queries)}）")
            
            # 添加一个小延迟，避免请求过快
            time.sleep(0.5)
            
        except Exception as e:
            print(f"  ❌ 失败: {e}")
            # 可选：保存错误标记
            error_item = {
                "query": query,
                "id": trajectory_map[query]["id"],
                "path": trajectory_map[query]["path"],
                "steprules": f"ERROR: {e}",
                "error": True
            }
            results.append(error_item)
            save_result(results)
            print(f"  ⚠️ 已保存错误标记，继续处理下一条")
    
    print("\n" + "=" * 60)
    print(f"🎉 全部处理完成！")
    print(f"总处理: {len(results)} 条")
    print(f"成功: {len([r for r in results if 'error' not in r])} 条")
    print(f"失败: {len([r for r in results if 'error' in r])} 条")
    print(f"结果已保存至: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()