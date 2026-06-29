---
license: Apache License 2.0
library_name: PaddleOCR
language:
- English
- Chinese
pipeline_tag: image-to-text
tags:
- OCR
- PaddlePaddle
- PaddleOCR
---

# PP-LCNet_x1_0_doc_ori

## Introduction

The Document Image Orientation Classification Module is primarily designed to distinguish the orientation of document images and correct them through post-processing. During processes such as document scanning or ID photo capturing, the device might be rotated to achieve clearer images, resulting in images with various orientations. Standard OCR pipelines may not handle these images effectively. By leveraging image classification techniques, the orientation of documents or IDs containing text regions can be pre-determined and adjusted, thereby improving the accuracy of OCR processing. The key accuracy metrics are as follow:

<table>
<tr>
<th>Model</th>
<th>Recognition Avg Accuracy(%)</th>
<th>Model Storage Size (M)</th>
<th>Introduction</th>
</tr>
<tr>
<td>PP-LCNet_x1_0_doc_ori</td>
<td>99.06</td>
<td>7</td>
<td>A document image classification model based on PP-LCNet_x1_0, with four categories: 0°, 90°, 180°, and 270°.</td>
</tr>
</table>

## Quick Start

### Installation

1. PaddlePaddle

Please refer to the following commands to install PaddlePaddle using pip:

```bash
# for CUDA11.8
python -m pip install paddlepaddle-gpu==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/

# for CUDA12.6
python -m pip install paddlepaddle-gpu==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/

# for CPU
python -m pip install paddlepaddle==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
```

For details about PaddlePaddle installation, please refer to the [PaddlePaddle official website](https://www.paddlepaddle.org.cn/en/install/quick).

2. PaddleOCR

Install the latest version of the PaddleOCR inference package from PyPI:

```bash
python -m pip install paddleocr
```

### Model Usage

You can quickly experience the functionality with a single command:

```bash
paddleocr doc_img_orientation_classification \
    --model_name PP-LCNet_x1_0_doc_ori \
    -i https://cdn-uploads.huggingface.co/production/uploads/681c1ecd9539bdde5ae1733c/4ifXaBJmFByG_mAnF86Vv.png
```

You can also integrate the model inference of the text recognition module into your project. Before running the following code, please download the sample image to your local machine.

```python
from paddleocr import DocImgOrientationClassification
model = DocImgOrientationClassification(model_name="PP-LCNet_x1_0_doc_ori")
output = model.predict(input="4ifXaBJmFByG_mAnF86Vv.png", batch_size=1)
for res in output:
    res.print()
    res.save_to_img(save_path="./output/")
    res.save_to_json(save_path="./output/res.json")
```

After running, the obtained result is as follows:

```json
{'res': {'input_path': '/root/.paddlex/predict_input/4ifXaBJmFByG_mAnF86Vv.png', 'page_index': None, 'class_ids': array([2], dtype=int32), 'scores': array([0.90971], dtype=float32), 'label_names': ['180']}}
```

The visualized image is as follows:

![image/jpeg](https://cdn-uploads.huggingface.co/production/uploads/681c1ecd9539bdde5ae1733c/DU_k30fxijLXFdXl179-0.png)

For details about usage command and descriptions of parameters, please refer to the [Document](https://paddlepaddle.github.io/PaddleOCR/latest/en/version3.x/module_usage/text_recognition.html#iii-quick-start).

### Pipeline Usage

The ability of a single model is limited. But the pipeline consists of several models can provide more capacity to resolve difficult problems in real-world scenarios.

#### doc_preprocessor

The Document Image Preprocessing Pipeline integrates two key functions: document orientation classification and geometric distortion correction. The document orientation classification module automatically identifies the four possible orientations of a document (0°, 90°, 180°, 270°), ensuring that the document is processed in the correct direction. The text image unwarping model is designed to correct geometric distortions that occur during document photography or scanning, restoring the document's original shape and proportions. This pipeline is suitable for digital document management, preprocessing tasks for OCR, and any scenario requiring improved document image quality. By automating orientation correction and geometric distortion correction, this module significantly enhances the accuracy and efficiency of document processing, providing a more reliable foundation for image analysis. The pipeline also offers flexible service-oriented deployment options, supporting calls from various programming languages on multiple hardware platforms. Additionally, the pipeline supports secondary development, allowing you to fine-tune the models on your own datasets and seamlessly integrate the trained models. And there are 2 modules in the pipeline: 
* Document Image Orientation Classification Module (Optional)
* Text Image Unwarping Module (Optional)

Run a single command to quickly experience the OCR pipeline:

```bash
paddleocr doc_preprocessor -i https://cdn-uploads.huggingface.co/production/uploads/681c1ecd9539bdde5ae1733c/pY6sY6wLDuoHF1-cGUvDr.png \
    --use_doc_orientation_classify True \
    --use_doc_unwarping True \
    --doc_orientation_classify_model_name PP-LCNet_x1_0_doc_ori \
    --save_path ./output \
    --device gpu:0 
```

Results are printed to the terminal:

```json
{'res': {'input_path': '/root/.paddlex/predict_input/pY6sY6wLDuoHF1-cGUvDr.png', 'page_index': None, 'model_settings': {'use_doc_orientation_classify': True, 'use_doc_unwarping': True}, 'angle': 180}}
```

If save_path is specified, the visualization results will be saved under `save_path`. The visualization output is shown below:

![image/jpeg](https://cdn-uploads.huggingface.co/production/uploads/681c1ecd9539bdde5ae1733c/HM8xQKtyBHx-CNVGk2ZJd.png)

The command-line method is for quick experience. For project integration, also only a few codes are needed as well:

```python
from paddleocr import DocPreprocessor  

ocr = DocPreprocessor(
    doc_orientation_classify_model_name="PP-LCNet_x1_0_doc_ori",
    use_doc_orientation_classify=True, # Use use_doc_orientation_classify to enable/disable document orientation classification model
    use_doc_unwarping=True, # Use use_doc_unwarping to enable/disable document unwarping module
    device="gpu:0", # Use device to specify GPU for model inference
)
result = ocr.predict("https://cdn-uploads.huggingface.co/production/uploads/681c1ecd9539bdde5ae1733c/pY6sY6wLDuoHF1-cGUvDr.png")  
for res in result:  
    res.print()  
    res.save_to_img("output")  
    res.save_to_json("output")
```

## Links

[PaddleOCR Repo](https://github.com/paddlepaddle/paddleocr)

[PaddleOCR Documentation](https://paddlepaddle.github.io/PaddleOCR/latest/en/index.html)
