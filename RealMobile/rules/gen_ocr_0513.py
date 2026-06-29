import os
import json
from pathlib import Path

# 获取当前文件所在目录
CURRENT_DIR = Path(__file__).parent
MODEL_DIR = CURRENT_DIR / 'paddle'

# 设置环境变量
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'


from paddleocr import PaddleOCR
import re
import time

def load_trajectory_paths(summary_file):
    """
    从 summary JSON 文件中加载所有非 a_ 开头的轨迹路径
    
    Args:
        summary_file: summary JSON 文件路径
    
    Returns:
        list: 轨迹信息列表 [{id, relative_path}]
    """
    with open(summary_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    trajectories = []
    for traj in data.get("trajectories", []):
        traj_id = traj.get("id")
        # 只处理非 a_ 开头的 ID（数字ID）
        if isinstance(traj_id, int):
            trajectories.append({
                "id": traj_id,
                "relative_path": traj.get("relative_path", "")
            })
    
    print(f"找到 {len(trajectories)} 个有效轨迹路径（非 a_ 开头）")
    return trajectories

def is_valid_step_file(filename):
    """判断是否为有效的步骤截图文件（只处理纯数字的 .png）"""
    pattern = r'^\d+\.png$'
    return re.match(pattern, filename, re.IGNORECASE) is not None

def extract_ocr_text_from_result(result):
    """从 PaddleOCR 返回的结果中提取文本和置信度"""
    ocr_results = []
    
    # PaddleOCR 返回格式通常是 list of list
    if result and isinstance(result, list):
        for line in result:
            if line and len(line) > 0:
                for item in line:
                    if len(item) >= 2:
                        # item[0] 是坐标，item[1] 是 (text, confidence)
                        box = item[0]
                        text_info = item[1]
                        text = text_info[0]
                        confidence = text_info[1]
                        
                        if text and text.strip() and confidence > 0.1:
                            ocr_results.append({
                                "text": text,
                                "confidence": float(confidence),
                                "box": box if isinstance(box, list) else box.tolist()
                            })
    
    return ocr_results

def batch_ocr_for_trajectories(
    summary_file="./rules/trajectory_summary_0513.json",
    base_dir=".",
    output_base_dir="./ocr_results",
    lang='ch',
    use_angle_cls=True,
    save_format='json'
):
    """为轨迹中的每个步骤截图进行 OCR 识别"""

    os.environ['PADDLEOCR_LOG_LEVEL'] = 'ERROR'

    # 1. 加载轨迹路径
    print(f"加载轨迹数据: {summary_file}")
    trajectories = load_trajectory_paths(summary_file)
    
    if not trajectories:
        print("没有找到轨迹数据")
        return

    # 2. 收集所有需要处理的图片
    all_images = []
    for traj in trajectories:
        traj_id = traj["id"]
        rel_path = traj["relative_path"]
        
        # 构建完整路径
        img_dir = Path(base_dir) / rel_path
        
        if not img_dir.exists():
            print(f"⚠️ 目录不存在: {img_dir}")
            continue
        
        # 查找所有数字命名的 PNG 文件（1.png, 2.png...）
        all_png_files = list(img_dir.glob("*.png")) + list(img_dir.glob("*.PNG"))
        step_png_files = [f for f in all_png_files if is_valid_step_file(f.name)]
        step_png_files.sort(key=lambda x: int(x.stem))  # 按数字排序
        
        for png_path in step_png_files:
            all_images.append({
                "traj_id": traj_id,
                "rel_path": rel_path,
                "png_path": png_path,
                "step_num": int(png_path.stem)
            })
    
    total_images = len(all_images)
    print(f"总共需要处理 {total_images} 张图片")
    print("=" * 80)
    
    if total_images == 0:
        print("没有需要处理的图片")
        return
    
    # 3. 初始化 OCR
    print("正在初始化 PaddleOCR...")
    start_time = time.time()
    ocr = PaddleOCR(use_angle_cls=use_angle_cls, lang=lang,
        det_model_dir=str(MODEL_DIR / 'det/PP-OCRv4_mobile_det_infer'),
        rec_model_dir=str(MODEL_DIR / 'rec/PP-OCRv4_mobile_rec_infer'),
        cls_model_dir=str(MODEL_DIR / 'cls/ch_ppocr_mobile_v2.0_cls_infer'),)
    print(f"初始化完成！耗时: {time.time() - start_time:.2f} 秒")
    print("=" * 80)
    
    # 4. 处理图片
    success_count = 0
    failed_count = 0
    total_texts = 0
    start_batch_time = time.time()
    
    for idx, img_info in enumerate(all_images, 1):
        png_path = img_info["png_path"]
        traj_id = img_info["traj_id"]
        rel_path = img_info["rel_path"]
        step_num = img_info["step_num"]
        
        # 创建输出目录（保持相同的目录结构）
        output_dir = Path(base_dir) / rel_path
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 输出文件路径（与 PNG 同名，但扩展名为 .json）
        output_file = output_dir / f"{step_num}.json"
        
        # 计算进度和时间
        elapsed = time.time() - start_batch_time
        avg_time = elapsed / (idx - 1) if idx > 1 else 0
        remaining = avg_time * (total_images - idx + 1)
        
        print(f"\n[{idx}/{total_images}] 轨迹 {traj_id} - 步骤 {step_num}.png")
        print(f"  路径: {rel_path}")
        print(f"  进度: {idx/total_images*100:.1f}% | 已用时: {elapsed/60:.1f}分钟 | 预计剩余: {remaining/60:.1f}分钟")
        
        try:
            start_img = time.time()
            
            # 执行 OCR
            result = ocr.ocr(str(png_path), cls=True)
            
            # 提取 OCR 结果
            ocr_results = extract_ocr_text_from_result(result)
            total_texts += len(ocr_results)
            
            # 保存 JSON
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(ocr_results, f, ensure_ascii=False, indent=2)
            
            img_time = time.time() - start_img
            success_count += 1
            
            # 打印识别结果预览
            if ocr_results:
                texts_preview = [item['text'][:20] for item in ocr_results[:3]]
                print(f"  ✅ 成功 ({img_time:.1f}s) - 识别 {len(ocr_results)} 条: {', '.join(texts_preview)}")
            else:
                print(f"  ✅ 成功 ({img_time:.1f}s) - 未识别到文本")
                
        except Exception as e:
            failed_count += 1
            print(f"  ❌ 失败: {e}")
            
            # 保存错误信息
            error_file = output_dir / f"{step_num}_error.txt"
            with open(error_file, 'w', encoding='utf-8') as f:
                f.write(f"OCR 失败: {e}\n")
    
    # 5. 最终统计
    total_time = time.time() - start_batch_time
    print("\n" + "=" * 80)
    print("批量 OCR 识别完成！")
    print(f"处理图片总数: {success_count + failed_count}")
    print(f"成功: {success_count} 张")
    print(f"失败: {failed_count} 张")
    print(f"识别的文本总数: {total_texts} 条")
    print(f"总耗时: {total_time/60:.1f} 分钟")
    print(f"平均每张: {total_time/(success_count+failed_count):.1f} 秒")
    print(f"OCR 结果保存在: {output_base_dir}")
    print("=" * 80)

def main():
    print("=" * 80)
    print("轨迹截图 OCR 识别工具")
    print("=" * 80)
    
    # 配置
    config = {
        "summary_file": "./rules/trajectory_summary_0513.json",
        "base_dir": ".",  # 相对于当前目录
        "output_base_dir": ".",
        "lang": "ch",
        "use_angle_cls": True
    }
    
    print(f"\n输入文件: {config['summary_file']}")
    print(f"基础目录: {config['base_dir']}")
    print(f"输出目录: {config['output_base_dir']}")
    
    # 询问是否开始
    confirm = input("\n是否开始 OCR 识别？(y/n): ").strip().lower()
    
    if confirm == 'y':
        print("\n开始处理...\n")
        batch_ocr_for_trajectories(**config)
    else:
        print("已取消")

if __name__ == "__main__":
    main()