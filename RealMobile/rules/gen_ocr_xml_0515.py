import json
import xml.etree.ElementTree as ET
from typing import List, Tuple, Dict, Optional, Set
import os
from pathlib import Path
import re
from collections import defaultdict

def parse_bounds(bounds_str: str) -> Tuple[int, int, int, int]:
    """
    解析bounds字符串，格式如 "[x1,y1][x2,y2]"
    返回 (x1, y1, x2, y2)
    """
    match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
    if match:
        return (int(match.group(1)), int(match.group(2)), 
                int(match.group(3)), int(match.group(4)))
    return None

def calculate_iou(box1: List[int], box2: List[int]) -> float:
    """
    计算两个矩形框的IoU (Intersection over Union)
    """
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    
    if x2 <= x1 or y2 <= y1:
        return 0.0
    
    intersection = (x2 - x1) * (y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection
    
    return intersection / union if union > 0 else 0.0

def calculate_center_distance(box1: List[int], box2: List[int]) -> float:
    """
    计算两个矩形框中心的距离
    """
    center1 = ((box1[0] + box1[2]) / 2, (box1[1] + box1[3]) / 2)
    center2 = ((box2[0] + box2[2]) / 2, (box2[1] + box2[3]) / 2)
    return ((center1[0] - center2[0]) ** 2 + (center1[1] - center2[1]) ** 2) ** 0.5

def text_matches(text1: str, text2: str) -> bool:
    """
    检查两个文本是否完全匹配
    """
    if not text1 or not text2:
        return False
    return text1.strip().lower() == text2.strip().lower()

def text_contains(text1: str, text2: str) -> bool:
    """
    检查一个文本是否包含另一个文本
    """
    if not text1 or not text2:
        return False
    return text2.strip().lower() in text1.strip().lower()

def collect_ui_elements(xml_root) -> List[Dict]:
    """
    遍历XML树，收集所有UI元素及其属性
    """
    elements = []
    
    def traverse(node, path="", depth=0):
        bounds_str = node.get('bounds', '')
        bounds = parse_bounds(bounds_str)
        
        if bounds:
            element = {
                'node': node,
                'bounds': bounds,
                'text': node.get('text', ''),
                'content_desc': node.get('content-desc', ''),
                'resource_id': node.get('resource-id', ''),
                'class': node.get('class', ''),
                'clickable': node.get('clickable', 'false') == 'true',
                'path': path,
                'depth': depth
            }
            elements.append(element)
        
        for i, child in enumerate(node):
            traverse(child, f"{path}/{i}", depth + 1)
    
    traverse(xml_root)
    return elements

def find_matching_elements(ocr_item: Dict, ui_elements: List[Dict], 
                          max_matches: int = 3) -> List[Dict]:
    """
    为单个OCR项找到匹配的UI元素，限制最大匹配数量
    优先级：完全文本匹配 > 文本包含 > 位置重叠 > 最近元素
    """
    ocr_text = ocr_item['text']
    if not ocr_text.strip():
        return []
    
    ocr_box = ocr_item['box']
    x_coords = [p[0] for p in ocr_box]
    y_coords = [p[1] for p in ocr_box]
    ocr_bbox = [min(x_coords), min(y_coords), max(x_coords), max(y_coords)]
    
    matches = []
    
    for ui_elem in ui_elements:
        ui_bounds = ui_elem['bounds']
        ui_text = ui_elem['text']
        ui_content_desc = ui_elem['content_desc']
        
        # 计算匹配度
        match_score = 0
        match_type = None
        
        # 优先级1: 完全文本匹配 (最高优先级)
        if text_matches(ocr_text, ui_text) or text_matches(ocr_text, ui_content_desc):
            match_score = 100
            match_type = 'exact_text'
        # 优先级2: 文本包含关系
        elif text_contains(ui_text, ocr_text) or text_contains(ui_content_desc, ocr_text):
            match_score = 80
            match_type = 'contains_text'
        elif text_contains(ocr_text, ui_text) or text_contains(ocr_text, ui_content_desc):
            match_score = 70
            match_type = 'text_subset'
        # 优先级3: 位置重叠
        else:
            iou = calculate_iou(ocr_bbox, ui_bounds)
            if iou > 0.1:  # IoU阈值
                match_score = 50 + iou * 30
                match_type = 'position_overlap'
            else:
                # 检查是否靠近（距离阈值100像素）
                distance = calculate_center_distance(ocr_bbox, ui_bounds)
                if distance < 100:
                    match_score = 30 - distance / 5
                    match_type = 'nearby'
        
        if match_score > 0:
            matches.append({
                'element': ui_elem,
                'match_type': match_type,
                'score': match_score,
                'iou': calculate_iou(ocr_bbox, ui_bounds),
                'distance': calculate_center_distance(ocr_bbox, ui_bounds),
                'ocr_text': ocr_text,
                'ui_text': ui_text
            })
    
    # 按得分排序，取前max_matches个
    matches.sort(key=lambda x: x['score'], reverse=True)
    
    # 特殊情况：如果没有找到任何匹配，但有精确文本匹配的候选（可能被过滤了）
    # 这种情况不应该发生，因为精确匹配会得到高分
    
    # 限制数量，但至少保留1个
    if len(matches) > max_matches:
        # 检查是否有精确匹配，如果有就只保留精确匹配和不冲突的
        exact_matches = [m for m in matches if m['match_type'] == 'exact_text']
        if exact_matches:
            # 如果有精确匹配，就只保留精确匹配（最多max_matches个）
            matches = exact_matches[:max_matches]
        else:
            matches = matches[:max_matches]
    
    return matches

def add_ocr_to_element(element_node, ocr_text: str, match_type: str, 
                      iou: float = None, distance: float = None):
    """
    为元素节点添加OCR相关信息
    """
    # 获取现有的ocr_texts
    existing = element_node.get('ocr_texts', '')
    existing_list = existing.split('|') if existing else []
    
    # 避免重复添加相同的OCR文本
    if ocr_text not in existing_list:
        if existing:
            element_node.set('ocr_texts', f"{existing}|{ocr_text}")
        else:
            element_node.set('ocr_texts', ocr_text)
    
    # 添加匹配类型（只记录最佳匹配类型）
    existing_types = element_node.get('ocr_match_types', '')
    if match_type not in existing_types.split('|'):
        if existing_types:
            element_node.set('ocr_match_types', f"{existing_types}|{match_type}")
        else:
            element_node.set('ocr_match_types', match_type)
    
    # 记录最佳的IoU
    if iou is not None and iou > 0:
        current_iou = element_node.get('ocr_max_iou', '0')
        if float(current_iou) < iou:
            element_node.set('ocr_max_iou', f"{iou:.3f}")
    
    # 记录最近距离
    if distance is not None:
        current_dist = element_node.get('ocr_min_distance', '999999')
        if float(current_dist) > distance:
            element_node.set('ocr_min_distance', f"{distance:.1f}")

def create_enriched_xml(original_xml_root, all_matches: List[Dict]):
    """
    创建带有OCR映射的增强XML
    """
    import copy
    new_root = copy.deepcopy(original_xml_root)
    
    # 建立bounds到节点的映射
    node_map = defaultdict(list)
    
    def build_node_map(node):
        bounds_str = node.get('bounds', '')
        if bounds_str:
            node_map[bounds_str].append(node)
        for child in node:
            build_node_map(child)
    
    build_node_map(new_root)
    
    # 为所有匹配的元素添加OCR属性
    for match in all_matches:
        element = match['element']
        bounds_str = element['node'].get('bounds', '')
        
        if bounds_str in node_map:
            for node in node_map[bounds_str]:
                add_ocr_to_element(
                    node, 
                    match['ocr_text'],
                    match['match_type'],
                    match.get('iou'),
                    match.get('distance')
                )
    
    return new_root

def process_step(step_dir: Path, step_num: int, max_matches_per_ocr: int = 3) -> Optional[ET.Element]:
    """
    处理单个步骤的XML和OCR文件
    """
    xml_file = step_dir / f"{step_num}.xml"
    ocr_file = step_dir / f"{step_num}.json"
    
    if not xml_file.exists() or not ocr_file.exists():
        print(f"  跳过步骤 {step_num}: 缺少文件")
        return None
    
    print(f"  处理步骤 {step_num}...")
    
    # 读取OCR结果
    with open(ocr_file, 'r', encoding='utf-8') as f:
        ocr_data = json.load(f)
    
    # 处理不同的OCR数据格式
    if isinstance(ocr_data, dict):
        # 尝试获取实际的OCR结果列表
        if 'ocr_results' in ocr_data:
            ocr_items = ocr_data['ocr_results']
        elif 'results' in ocr_data:
            ocr_items = ocr_data['results']
        elif 'data' in ocr_data:
            ocr_items = ocr_data['data']
        else:
            # 如果是其他字典格式，尝试找出包含列表的键
            ocr_items = []
            for key, value in ocr_data.items():
                if isinstance(value, list) and len(value) > 0:
                    if isinstance(value[0], dict) and 'text' in value[0]:
                        ocr_items = value
                        break
    elif isinstance(ocr_data, list):
        ocr_items = ocr_data
    else:
        print(f"    未知的OCR数据格式: {type(ocr_data)}")
        return None
    
    # 如果ocr_items为空或不是预期的格式，尝试从OCR文件直接读取文本列表
    if not ocr_items:
        # 某些OCR文件可能直接存储文本列表
        alt_ocr_file = step_dir / f"{step_num}_ocr.txt"
        if alt_ocr_file.exists():
            with open(alt_ocr_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                ocr_items = [{'text': line.strip(), 'box': [[0,0],[0,0],[0,0],[0,0]]} 
                           for line in lines if line.strip()]
    
    # 解析XML
    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    # 收集所有UI元素
    ui_elements = collect_ui_elements(root)
    print(f"    找到 {len(ui_elements)} 个UI元素")
    print(f"    找到 {len(ocr_items)} 个OCR文本")
    
    # 如果没有OCR文本，直接返回原XML
    if not ocr_items:
        print(f"    警告: 没有OCR文本数据")
        return root
    
    # 为每个OCR文本找到匹配的UI元素
    all_matches = []
    match_stats = {'exact': 0, 'contains': 0, 'position': 0, 'nearby': 0, 'total_ocr': 0}
    
    for ocr_item in ocr_items:
        # 处理不同的OCR项格式
        if isinstance(ocr_item, str):
            # 如果是字符串，创建基本结构
            ocr_text = ocr_item
            ocr_box = [[0,0],[0,0],[0,0],[0,0]]  # 没有位置信息
        elif isinstance(ocr_item, dict):
            ocr_text = ocr_item.get('text', '')
            ocr_box = ocr_item.get('box', [[0,0],[0,0],[0,0],[0,0]])
        else:
            continue
            
        if not ocr_text.strip():
            continue
            
        match_stats['total_ocr'] += 1
        matches = find_matching_elements({'text': ocr_text, 'box': ocr_box}, 
                                        ui_elements, max_matches_per_ocr)
        
        if matches:
            all_matches.extend(matches)
            
            # 统计匹配类型
            for match in matches:
                match_stats[match['match_type']] = match_stats.get(match['match_type'], 0) + 1
            
            # 打印匹配信息（只显示前3个匹配）
            match_info = []
            for i, match in enumerate(matches[:3]):
                match_info.append(f"{match['match_type']}({match['score']:.0f})")
            print(f"    匹配 '{ocr_text}': {len(matches)} 个元素 [{', '.join(match_info)}]")
        else:
            print(f"    未匹配 '{ocr_text}'")
    
    # 打印统计信息
    if match_stats['total_ocr'] > 0:
        print(f"    匹配统计: 成功匹配OCR {len(set([m['ocr_text'] for m in all_matches]))}/{match_stats['total_ocr']} 个")
        print(f"    匹配详情: 精确={match_stats.get('exact_text', 0)}, "
              f"包含={match_stats.get('contains_text', 0)+match_stats.get('text_subset', 0)}, "
              f"位置重叠={match_stats.get('position_overlap', 0)}, "
              f"附近={match_stats.get('nearby', 0)}")
    
    # 创建增强的XML
    if all_matches:
        enriched_root = create_enriched_xml(root, all_matches)
        return enriched_root
    else:
        print(f"    警告: 没有找到任何匹配")
        return root  # 返回原始XML而不是None

def process_all_steps(base_dir: Path, step_numbers: List[int]):
    """
    批量处理所有步骤
    """
    for step_num in step_numbers:
        enriched_root = process_step(base_dir, step_num, max_matches_per_ocr=3)
        
        if enriched_root is not None:
            output_file = base_dir / f"{step_num}_ocr.xml"
            tree = ET.ElementTree(enriched_root)
            tree.write(output_file, encoding='utf-8', xml_declaration=True)
            print(f"    保存到: {output_file}")

def main():
    # 读取查询步骤轨迹文件
    config_file = Path("rules/trajectory_summary_0515.json")
    
    if not config_file.exists():
        print(f"配置文件不存在: {config_file}")
        return
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    merged_data = config.get('trajectories', [])
    print(f"找到 {len(merged_data)} 个查询任务")
    
    for item in merged_data:
        query = item.get('query', '')
        path_list = item.get('path_list', '')
        query_id = item.get('id', 0)
        
        print(f"\n{'='*60}")
        print(f"处理查询 [{query_id}]: {query}")
        

        for path_json in path_list:
            path=path_json["path"]
            print(f"路径: {path_list}")
            
            base_dir = Path(path)
            if not base_dir.exists():
                print(f"  目录不存在: {base_dir}")
                continue
            
            # 收集所有步骤文件
            xml_files = sorted(base_dir.glob("*.xml"))
            #xml_files = [f for f in xml_files if not f.name.endswith('_ocr.xml')]
            
            step_numbers = []
            for xml_file in xml_files:
                step_name = xml_file.stem
                if step_name.isdigit():
                    step_numbers.append(int(step_name))
            
            step_numbers.sort()
            print(f"  找到 {len(step_numbers)} 个步骤: {step_numbers}")
            
            process_all_steps(base_dir, step_numbers)

if __name__ == "__main__":
    main()